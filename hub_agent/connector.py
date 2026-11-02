"""连接器的回环健康探测；不提供本机网页、登录或业务接口。"""
from aiohttp import web


class ERPRequestError(RuntimeError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class ConnectorServer:
    def __init__(self, state, portal_url, host="127.0.0.1", port=45679):
        self.state, self.host, self.port = state, host, port
        self.origins = {"https://erp.haitorok.com", "http://localhost:5173", "http://127.0.0.1:5173", portal_url}
        self.runner = None

    def app(self):
        @web.middleware
        async def security(request, handler):
            origin = request.headers.get("Origin")
            if request.host != f"{self.host}:{self.port}" or origin and origin not in self.origins:
                raise web.HTTPForbidden()
            response = await handler(request)
            response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
            if origin:
                response.headers.update({"Access-Control-Allow-Origin": origin, "Vary": "Origin"})
                if request.method == "OPTIONS":
                    response.headers.update({"Access-Control-Allow-Methods": "GET", "Access-Control-Allow-Private-Network": "true"})
            return response

        app = web.Application(middlewares=[security])
        app.router.add_get("/health", self.health)
        app.router.add_options("/health", self.preflight)
        return app

    async def health(self, request):
        return web.json_response({"application": "haitoo-hub-agent", "protocol": 5, "mode": "connector", "status": "ready"})

    async def preflight(self, request):
        if request.headers.get("Access-Control-Request-Method") != "GET" or request.headers.get("Access-Control-Request-Headers"):
            raise web.HTTPForbidden()
        return web.Response(status=204)

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
