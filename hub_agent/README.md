# Haitoo HubStudio 连接器

本机连接器连接当前桌面用户的 HubStudio，获取环境、上传目录并执行 ERP 下发的矩阵任务。设备、环境、方案、运行、日志及人工处理统一在 ERP 的“TK 矩阵”页面管理。本机不提供工作页、账号密码登录页或业务接口。

连接器必须以员工当前桌面用户运行，不能部署在 ERP 服务器，也不能作为 Windows Service 运行。关闭 ERP 网页不影响已创建的服务器任务；退出连接器会使该电脑离线。

## 首次连接

1. 请公司管理员先在「企业管理 → 矩阵管理 → 成员授权」开放矩阵使用权限；再启动并登录 HubStudio，确认当前团队及 Local API 可用。
2. 完整解压安装包，运行 macOS 的 `启动并配对.command` 或 Windows 的 `启动并配对.cmd`。日常也可运行托盘程序。
3. 首次启动自动打开 ERP 的“TK 矩阵”页面。使用 ERP 账号登录，确认是自己启动的连接器后，点击“授权此电脑连接器”。账号密码只在 ERP 登录，电脑令牌仅保存到系统凭据库。
4. 在 ERP 的“设备管理”中配置当前 HubStudio 团队的稳定 ID。同一团队的多台电脑填写相同 ID；不能用电脑名或邮箱代替。当前已验证的 Local API 列表契约未提供可信的团队身份查询，因此这一项由 ERP 保存，下发给连接器。
5. 公司管理员在「企业管理 → 矩阵管理 → 功能设置」启用矩阵功能。连接器自动获取完整环境并上传服务器，环境出现在 ERP 列表中；也可在 ERP 点击“同步环境”。

已有有效电脑授权直接重连；授权失效后重新打开 ERP 配对页面。配对链接十分钟有效，不把电脑令牌放进 URL，也不把 ERP 登录令牌发给回环服务。更新时保留安装身份和配置，不覆盖原有日志或系统凭据。

本机 `127.0.0.1:45679` 只保留 `/health`，供 ERP 检测连接器是否运行，不提供 HTML、业务数据或任务控制。浏览器提示本地网络访问权限时，允许后可正常检测。托盘菜单只提供状态、打开 ERP 和退出。

## 环境与任务

- 连接器每 60 秒从 HubStudio 当前用户及团队获取完整目录。所有分页成功后，按白名单分片上传，服务器原子提交。失败保留上次完整目录，不用部分结果覆盖。
- 环境名称、编号、分组及绑定账号名称可进入目录；密码、2FA 密钥、代理凭据和 IP 不上传。ERP 按公司及设备访问关系展示环境。
- Hub 团队身份在 ERP 保存。修改身份会清除该设备的旧目录访问关系，等待重新同步；设备有排队、运行中或待人工处理的运行时，禁止修改身份。
- 方案、定时、站点覆盖、任务预览、执行、停止及人工处理都在 ERP 操作。公司开关与成员的采集、上品授权均由服务端校验；收回权限后不接新任务，已有任务收到停止请求并保留结果记录。新版连接器只领取 ERP 矩阵任务，不再使用旧本机策略领取协议4任务。历史上品记录和锁保留，旧任务需先核对平台结果再处理。
- 超过五分钟未成功上传的目录不用于领取新的浏览器任务；固定采集包重传不重新打开浏览器。同环境任务继续使用服务器串行锁和 fencing。
- 当前仅启用马来西亚（MY）跨境店，商品入口为 `https://seller.tiktokshopglobalselling.com/product/manage?shop_region=MY`。按站点与店铺类型维护入口配置，不回退到本土卖家中心；采集固定使用内置跨境适配。其他站点与本土店暂不支持。公司和成员授权仍由 ERP 控制；能力声明不代表真实页面验收。自动上品仍需签名插件与实际站点验收。
- 连接器使用当前 HubStudio 登录态，不切换团队；按选中的环境编号启动浏览器并打开商品管理页，不再请求或等待平台店铺身份接口；结果按环境归档。页面登录失效或采集失败时保留本次页面供人工核查，不关闭用户已有页面。

## 本机开发

后端使用项目的本机 Docker 环境，前端优先使用 Vite 热更新。连接器直接运行源码，修改后重启即可，不需要重新打包。先退出已有连接器以释放 45679 端口。

在项目根目录运行：

```bash
export HAITOO_LOCAL_DEBUG=1
export HAITOO_API_URL=http://127.0.0.1:8001
export HAITOO_PORTAL_URL=http://localhost:5173
.venv/bin/python hub_agent/haitoo_hub_agent.py console
```

显式启用本机调试后，仅允许回环 HTTP；其他地址仍要求 HTTPS。调试按 API 地址隔离系统凭据和默认配置、日志目录，不影响正式环境授权。`HAITOO_AGENT_DATA_DIR` 可指定开发配置与日志目录。连接器仍连接真实 HubStudio，请使用专用测试环境。

当前只读采集在浏览器登录会话中按商品列表接口读取 MY 跨境商品管理页“在售”的全部分页、商品ID、近28天浏览次数和完整SKU（平台SKU ID、规格、商家SKU、库存、MYR价格）。通过列表参数批量返回SKU，必要时读取SKU明细接口，无需逐个展开商品。无需日期筛选；商品分析、曝光和点击后续补充。浏览次数取接口 `last_28days_pv` 原值，`--`保持未知，不推断精确日期窗口。遇到安全验证时在本次页面提示人工处理，最多等待10分钟；不修改库存或价格。

只读采集由 ERP 后台授权后执行，无需本机配置。旧配置中的 `matrix_collection_validation_sites` 不再控制能力声明；Hub 团队身份始终在 ERP 配置。

回到正式环境前退出调试连接器，执行 `unset HAITOO_LOCAL_DEBUG HAITOO_API_URL HAITOO_PORTAL_URL` 后重启。默认正式 API 为 `https://api.haitorok.com`，ERP 为 `https://erp.haitorok.com`。

## 构建与分发

macOS 必须在 Mac 构建，Windows 必须在 Windows 构建：

```bash
cd hub_agent
./build_macos.sh
```

```powershell
cd hub_agent
.\build_windows.ps1 -RunTests
```

产物必须保留图形程序、控制台程序目录及启动脚本的相对位置。安装包不再打入本机工作页静态资源。正式分发需完成对应平台的代码签名；macOS 还需 Apple 公证。Windows 也可使用仓库中的“构建 Windows 本地执行器”Actions 工作流。

ERP 首次安装下载读取 `hub_agent/dist/HaitooHubAgent-<windows|macos>-<x64|arm64>-<三段版本>.zip`，Compose 将该目录只读挂载到 API；非 Compose 环境通过 `HUB_AGENT_INSTALLER_DIR` 指定。下载须有公司内部登录权限，不提供不存在的包。

连接器及插件在线升级使用 `trusted_keys.json` 或 `HAITOO_RELEASE_KEYS_FILE` 指定的公钥库。空公钥库拒绝远程包；签名、摘要、平台及协议须全部通过，任务中不切换版本。退出连接器后，可用 `rollback --kind agent` 或 `rollback --kind plugin` 恢复上一已验证版本。

## 验证与日志

在项目根目录运行：

```bash
PYTHONPATH=hub_agent .venv/bin/python -m unittest discover -s hub_agent/tests
PYTHONPATH=backend:backend/tests .venv/bin/python -m unittest discover -s backend/tests -p 'test_tk_matrix.py'
npm test --prefix frontend
npm run build --prefix frontend
```

健康探测测试只使用临时回环端口。浏览器专项通过显式 `HAITOO_BROWSER_TESTS=1` 启用，不使用用户店铺会话。

日志统一使用 UTF-8：macOS 默认 `~/Library/Logs/HaitooHubAgent/agent.log`，Windows 默认 `%LOCALAPPDATA%\HaitooHubAgent\agent.log`；本机调试使用对应 API 的隔离子目录。日志可能包含平台页面信息，排错时不要公开原文中的敏感数据。

具体平台验收状态见 [验证记录](../docs/tk-matrix-validation.md)，签名与快照契约见 [TK 矩阵设计](../docs/tk-matrix-upgrade-design.md)。
