# 本机 Agent 复刻：契约与实现说明

## 0. 一句话结论

对方的本机 Agent 不是"需要逆向的二进制"，而是 **本地 HTTP 服务 + 本地 SQLite 台账 + HubStudio 驱动 + 云票据 + 自更新 + 开机自启**。
它的控制台单页（`http://127.0.0.1:45690/`）本身就是完整的 API 文档，`curl` 一次就拿到，不需要脱壳。

## 1. 实测事实（2026-10-24，本机只读验证）

| 项 | 观测结果 |
|---|---|
| 进程 | `EB-Hub-Agent`，x86_64 Mach-O（Apple Silicon 上经 Rosetta 运行），65 MB |
| 监听端口 | `127.0.0.1:45690`（控制台）、`45694`、`45695`（状态面） |
| HubStudio | 本体监听 `127.0.0.1:6873`（官方 Local API） |
| 状态面 | `GET /status` 无鉴权、`Access-Control-Allow-Origin: *`，返回 `ok/device/hubstudio/version/pendingUpdate/user/ticket/accounts[]` |
| 控制台 | `GET /` 返回 655 KB 单页，含全部 `fetch('/api/...')` 调用 |
| 本地库 | `~/.eb-hub/matrix.db`（WAL），7 张表：`eb_shop / hub_env / shop_env_link / unlink_mark / env_shop_observation / import_run / audit_log` |
| 免密链路 | 网页登录页 `fetch('http://127.0.0.1:45695/status')` → `accounts[].ticket` → `POST /max/login/ticket` → 种 Cookie |
| 二进制静态分析 | `strings` 里 `yunwang` / `45695` / `hubstudio` / 中文串**均搜不到**（载荷压缩或加密），静态逆性价比极低，也没有必要 |

## 2. 契约对照表

| 对方路由 | 语义 | 本原型 | 状态 |
|---|---|---|---|
| `GET /status` | 设备/版本/账号/票据 | 同名 | ✅ 实现 |
| `GET /api/envs` | 环境清单（运行/隐藏/绑定） | 同名，实时读 HubStudio | ✅ 实现 |
| `GET /api/env/running` | 运行中环境与调试端口 | 同名 | ✅ 实现 |
| `POST /api/env/peek` / `unpeek` | 隐藏环境名 | 同名 | ✅ 实现 |
| `POST /api/run?device=` | 起环境跑任务 | 同名 + SSE 进度 | ✅ 实现（动作是占位） |
| `POST /api/stop` | 停批并回收环境 | 同名 | ✅ 实现 |
| `GET /api/stream?replay=inc\|none` | 运行日志流 | 同名，seq 补发 | ✅ 实现 |
| `GET /api/plans` / `POST /api/plans/op` | 执行方案 CRUD | 同名（本地 JSON） | ✅ 实现 |
| `/api/map/{links,bind,unbind,mark}` | 店铺↔环境台账 | 同名 + SQLite | ✅ 实现 |
| `/api/map/cloud{,/sync,/resolve}` | 台账上云与冲突裁决 | 本地对账 | 🟡 云端待接 |
| `/api/settings{,/cloud*}` | 设置（含云同步） | 本地实现 | 🟡 云端待接 |
| `GET /api/env-state` | 执行观测流 | 同名 | ✅ 实现 |
| `/api/yw/{login,status,logout,bind-team}` | 云往账号会话 | 由 ERP 侧承担 | ⬜ 未接 |
| `GET /api/update/state`、`POST /update/apply` | 自更新 | 只读状态 | 🟡 通道待接 |
| `GET /api/opportunity/*`、`/api/ops/*`、`/api/pp*`、`/api/tin/*`、`/api/imap*`、`/api/xinlan` | 商品机会、店铺运营、PINGPONG、TIN 清单、邮箱取件、心蓝 | 未实现 | ⬜ 业务插件，按需补 |

## 3. 数据模型（这是对方真正的资产）

绑定是**时段事实**，不是"当前值"：

```
shop(account, platform, platform_shop_id, site, auth_state, state…)
environment(team_no, container_code, name, grp, site, state…)
link(shop…, env…, match_method, confidence, evidence, valid_from, valid_to, closed_reason)
mark(人工标记：这对不绑)     observation(执行时观测到的店铺)     sync_run / audit
```

规则：

- `match_method`：`M0` 认领 / `M1` 名称精确 / `M2` 名称模糊 / `M9` 人工；`confidence` 只有 `confirmed` / `probable`。
- 唯一性靠**部分索引**：同一店铺或同一环境只能有一条 `valid_to IS NULL` 的绑定。
- 重绑先闭链（`closed_reason='rebind'`），历史不删；环境消失闭链为 `env_deleted`。
- `probable` 的绑定必须由人裁决，机器不许自己升级成 `confirmed`。

## 4. 免密登录：对方怎么做，我们该怎么做

对方时序：Agent 本地保存云往票据 → 网页读 `127.0.0.1:45695/status` → 拿 `ticket` → `POST /max/login/ticket` → 种会话 Cookie。

问题在于 `status` 是 `Access-Control-Allow-Origin: *` 且无鉴权：**任何你打开的网页都能读到你的账号名和票据**，也能 `POST /reconfig` 弹窗、`POST /update/apply` 触发升级。它把认证信任外包给了"本机回环地址"。

本原型的改法：

1. `GET /status` 仍允许跨源读，但只回**非敏感**字段（`ticket` 字段保留形状、值为空或一次性短票据）；
2. 所有 `/api/*` 变更必须带 `X-Agent-Token`（进程启动时生成，落在数据目录，权限 600）；
3. `Origin` 白名单（本机控制台 + 显式配置的 ERP 域名），其余 403；
4. 真要免密，票据应当是**一次性 + 60 秒 TTL + 绑定 Origin**。

## 5. 日志流：别用时间重叠

对方的控制台注释自述：断线重连按 30 秒重叠补发，实测同一行日志重复 6.5 遍，靠前端去重兜底。

本原型用单调 `seq` + SSE 标准 `id:` 字段，浏览器重连时自动带 `Last-Event-ID`，服务端只补 `seq >` 的事件，**结构上不会重复**。`replay=none` 用于新开页面只看实时。

## 6. 自更新

对方：`/agentdl/latest.json` 取版本，安装包放对象存储（带时间参数防缓存），`.update-state.json` 记录连败次数与最后原因。

建议不要照抄"下载 zip 覆盖自身"：至少要有 **包签名校验 + 版本回滚 + 失败计数熔断**，否则一次坏包会让整批机器起不来。

## 7. 落地清单（把原型变成产品）

1. `clone/server.py` 的 `_execute` 里把 `await asyncio.sleep(0.3)` 换成真实动作 —— 仓库里已有 `hubstudio.bound_account()` 取账号、`upload_and_import()` 走 Playwright，直接接；
2. 云端：票据签发/校验、`plans` 存储、`map` 三方合并（本地 / 云端 / 人工标记）冲突协议；
3. 常驻：`hub_agent/install/macos/com.haitoo.hub-agent.plist` 已有，补齐"关窗不退 + 开机自启 + 单实例锁"；
4. 打包：`HaitooHubAgent.spec` 建议 `--onedir` + 代码签名 + 公证，别发裸 zip；
5. 端口：建议收敛为一个端口（现有 `45679` workbench），别学对方三开；
6. 安全：补 Origin 白名单与 token（原型已做），并把 `settings.json` 里的密钥移到系统钥匙串（仓库已有 `keyring` 用法）。
