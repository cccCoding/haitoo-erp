"""只监听回环地址的本地工作页；浏览器不接触 ERP 或第三方密钥。"""
from pathlib import Path
import secrets
from aiohttp import web


class ERPRequestError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class LocalStatusServer:
    def __init__(self, state, client_getter=None, sync_callback=None, log_path=None, host="127.0.0.1", port=45679, login_callback=None, toggle_callback=None):
        self.state, self.client_getter, self.sync_callback = state, client_getter, sync_callback
        self.log_path, self.host, self.port = log_path, host, port
        self.origin = f"http://{host}:{port}"
        self.csrf = secrets.token_urlsafe(32)
        self.sessions = set()
        self.runner = None
        self.login_callback = login_callback
        self.toggle_callback = toggle_callback
        self.static = Path(__file__).resolve().parent / "static"

    def app(self):
        @web.middleware
        async def security(request, handler):
            if request.host != f"{self.host}:{self.port}":
                raise web.HTTPForbidden(text="无效本机地址")
            if request.path.startswith("/api/"):
                if request.cookies.get("hub_session") not in self.sessions:
                    raise web.HTTPForbidden(text="请重新打开本机工作页")
                origin = request.headers.get("Origin")
                if origin and origin != self.origin:
                    raise web.HTTPForbidden(text="拒绝跨站请求")
                if request.method not in {"GET", "HEAD"} and (origin != self.origin or not secrets.compare_digest(request.headers.get("X-CSRF-Token", ""), self.csrf)):
                    raise web.HTTPForbidden(text="本机会话校验失败")
            try:
                response = await handler(request)
            except ERPRequestError as exc:
                response = web.json_response({"detail": str(exc)}, status=exc.status)
            except web.HTTPException:
                raise
            except Exception:
                # 不将 HTTP 请求对象、认证头、URL 查询串或原始异常暴露给页面。
                response = web.json_response({"detail": "请求失败，请检查连接或本机日志"}, status=502)
            response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"})
            return response

        app = web.Application(middlewares=[security], client_max_size=64 * 1024)
        app.router.add_get("/", self.index)
        app.router.add_get("/health", self.health)
        app.router.add_get("/assets/{name}", self.asset)
        app.router.add_get("/api/status", self.status)
        app.router.add_post("/api/login", self.login)
        app.router.add_get("/api/environments", self.environments)
        app.router.add_post("/api/sync", self.sync)
        app.router.add_post("/api/pause", self.pause)
        app.router.add_put("/api/environments/{id}/auto-upload", self.toggle)
        app.router.add_get("/api/tasks", self.tasks)
        app.router.add_get("/api/tasks/{id}", self.task)
        app.router.add_post("/api/tasks/{id}/{action}", self.action)
        app.router.add_get("/api/logs", self.logs)
        return app

    async def start(self):
        self.runner = web.AppRunner(self.app(), access_log=None)
        await self.runner.setup()
        try:
            await web.TCPSite(self.runner, self.host, self.port).start()
        except Exception:
            await self.runner.cleanup()
            raise

    async def close(self):
        if self.runner:
            await self.runner.cleanup()

    async def index(self, request):
        session = request.cookies.get("hub_session")
        if session not in self.sessions:
            session = secrets.token_urlsafe(32)
            if len(self.sessions) >= 100:
                self.sessions.clear()
            self.sessions.add(session)
        response = web.Response(text=(self.static / "index.html").read_text(encoding="utf-8"), content_type="text/html")
        response.set_cookie("hub_session", session, httponly=True, samesite="Strict")
        return response

    async def asset(self, request):
        name = request.match_info["name"]
        if name not in {"workbench.js", "workbench.css"}:
            raise web.HTTPNotFound()
        return web.FileResponse(self.static / name)

    async def health(self, request):
        return web.json_response({"status": "ready"})

    async def status(self, request):
        safe = {k: self.state.get(k) for k in ("status", "paused", "user", "sync_at", "sync_error", "erp_connected", "hub_connected", "login_required")}
        return web.json_response(safe | {"csrf": self.csrf})

    async def login(self, request):
        payload = await request.json()
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(text="请输入邮箱和密码")
        email, password = payload.get("email"), payload.get("password")
        if not isinstance(email, str) or not email.strip() or len(email) > 320 or not isinstance(password, str) or not password or len(password) > 4096:
            raise web.HTTPBadRequest(text="请输入有效的邮箱和密码")
        if not self.login_callback:
            raise web.HTTPServiceUnavailable(text="当前版本不支持本地登录")
        await self.login_callback(email.strip(), password)
        return web.json_response({"ok": True})

    def client(self):
        client = self.client_getter() if self.client_getter else None
        if not client:
            raise web.HTTPServiceUnavailable(text="请在本地工作页登录 ERP 账号")
        return client

    async def proxy(self, method, path, **kwargs):
        result = await self.client().request(method, path, **kwargs)
        return web.json_response(result)

    async def environments(self, request):
        # 环境目录只在本机内存中展示，绝不向 ERP 上传或查询。
        return web.json_response(self.state.get("environments", []))

    async def sync(self, request):
        self.client()
        await self.sync_callback()
        return web.json_response({"ok": not bool(self.state.get("sync_error")), "detail": self.state.get("sync_error")})

    async def pause(self, request):
        payload = await request.json()
        if not isinstance(payload.get("paused"), bool):
            raise web.HTTPBadRequest()
        self.state["paused"] = payload["paused"]
        return web.json_response({"paused": self.state["paused"]})

    async def toggle(self, request):
        self.client()
        payload = await request.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool) or not isinstance(payload.get("confirmed_local", False), bool):
            raise web.HTTPBadRequest(text="环境开关参数无效")
        if not self.toggle_callback:
            raise web.HTTPServiceUnavailable(text="请升级执行器")
        result = await self.toggle_callback(request.match_info['id'], payload["enabled"], payload.get("confirmed_local", False))
        return web.json_response(result)

    async def tasks(self, request):
        params = {k: request.query[k] for k in ("page", "page_size", "status") if k in request.query}
        return await self.proxy("GET", "/hub-agent/tasks", params=params)

    async def task(self, request):
        return await self.proxy("GET", f"/hub-agent/tasks/{int(request.match_info['id'])}")

    async def action(self, request):
        action = request.match_info["action"]
        if action not in {"retry", "cancel", "confirm-submitted"}:
            raise web.HTTPNotFound()
        return await self.proxy("POST", f"/hub-agent/tasks/{int(request.match_info['id'])}/actions/{action}", json=await request.json())

    async def logs(self, request):
        lines = []
        if self.log_path and self.log_path.exists():
            # 只读文件尾部，避免长期运行日志撑满内存。
            with self.log_path.open("rb") as log:
                log.seek(0, 2); size = log.tell(); log.seek(max(0, size - 65536))
                lines = log.read().decode("utf-8", "replace").splitlines()[-100:]
        return web.json_response({"lines": lines})
