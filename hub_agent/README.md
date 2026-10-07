# Haitoo HubStudio 本地执行器

此执行器安装在员工电脑上，以安装 HubStudio 的当前桌面用户运行。ERP 保存账号任务和固定 XLSX；执行器只在本机内存同步当前可访问环境，原子领取本账号任务，在对应 HubStudio 环境内完成 TikTok 批量上传提交。环境无需管理员创建店铺、分配人员或绑定电脑。

它不是 Windows Service，也不能部署到 ERP 服务器。

## 部署前提

在首次运行本地执行器前，生产 ERP 必须已经发布包含 Hub 执行器接口的后端，并已执行迁移至 `20261007_30`。本地登录使用现有 `/auth/login` 和 `/hub-agents/register` 接口；若返回 HTTP 404，需检查 API 地址和服务器发布版本。

## 使用方式与安全边界

- 执行器默认请求 `https://api.haitorok.com`。首次启动在本地工作页输入 ERP 邮箱和密码，点击“登录并授权”，由本地程序调用 ERP 登录和电脑注册接口；密码及 ERP 登录 Token 不保存、不返回页面，系统凭据库只保存执行器 Token。腾讯云使用其他域名时，通过 `HAITOO_API_URL` 指定 HTTPS API 地址；显式配置会覆盖本机保存的旧 API 地址。已有电脑授权继续沿用，失效后重新显示登录表单。已授权时不提供切换账号，避免执行中的任务改变身份。
- 终端名称自动取电脑名称并附加短标识，避免同名电脑注册冲突；终端令牌仅保存到 macOS Keychain 或 Windows Credential Manager，不写入配置文件。
- 执行器提供本机工作页 `http://127.0.0.1:45679`，不监听局域网。工作页包含环境列表、本账号任务、执行尝试、日志和人工处理；浏览器不持有执行器 Token 或公司 Secret。页面关闭后执行器仍继续工作。
- TikTok 登录状态保留在 HubStudio 指纹环境内。ERP 不下发 TikTok 账号密码；若登录失效、验证码或页面校验失败，任务会进入人工处理。

## 本机 Docker 调试

先退出已有执行器（工作页端口 45679 共用），启动本机 Docker 环境：

```bash
cd /Users/rock/codespace/haitoo-erp
./deploy/local.sh up -d --build
export HAITOO_LOCAL_DEBUG=1
export HAITOO_API_URL="http://127.0.0.1:8001"
export HAITOO_PORTAL_URL="http://127.0.0.1:5173"
.venv/bin/python hub_agent/haitoo_hub_agent.py console
```

源码启动直接使用项目虚拟环境，修改代码后重启即可，无需重新打包。已打包的程序需重新构建，再在设置上述变量的同一终端执行 `bash hub_agent/dist/启动并配对.command`。

只有显式设置 `HAITOO_LOCAL_DEBUG=1` 才允许 HTTP，地址仅限 `127.0.0.1`、`localhost`、`::1`；其他地址仍要求 HTTPS。调试模式按 API 地址隔离钥匙串授权和默认配置、日志目录，首次在本地工作页使用本机数据库中的 ERP 账号登录授权。它仍会连接真实 HubStudio，执行任务也会操作真实店铺，请使用专用测试环境及商品。

回到正式环境前先退出调试执行器，并执行 `unset HAITOO_LOCAL_DEBUG HAITOO_API_URL HAITOO_PORTAL_URL`，然后重新启动。正式环境的原授权不受调试配对影响。

## 给员工的首次启动说明

未签名的内部测试包请优先双击 **启动并配对**，不要直接双击 App：

- macOS：双击 `启动并配对.command`。它会清除当前安装包的下载隔离标记、在 Terminal 显示运行日志，并在状态页可用后打开浏览器。
- Windows：双击 `启动并配对.cmd`。它会保留命令窗口显示错误，并在状态页可用后打开浏览器。

终端窗口不可关闭；关闭它等同于停止执行器。首次启动后，在本地工作页输入 ERP 邮箱和密码，点击“登录并授权”即可，无需跳转 ERP 网页。本机工作页显示授权、连接、环境和任务状态。同步环境后，为一个确认属于 TikTok 本土店的环境开启“允许自动上品”；本机只能启用一个环境，启用其他环境会自动关闭原环境，执行中不能切换。员工在 ERP 草稿页直接生成任务，无需选择环境；执行器自动领取并使用本机已启用环境。环境目录和访问关系不上传到 ERP、不写数据库，本机配置只保存唯一选择的环境 ID。跨境店环境仍可展示，但不要开启自动上品。

如果启动失败，请保留窗口并截图最后的错误信息，同时提供日志文件：

- macOS：`~/Library/Logs/HaitooHubAgent/agent.log`
- Windows：`%LOCALAPPDATA%\HaitooHubAgent\agent.log`

## macOS 构建与分发

必须在 Mac 上构建：

```bash
cd /Users/rock/codespace/haitoo-erp/hub_agent
chmod +x build_macos.sh
./build_macos.sh
```

构建结果在 `dist/`，发布时必须把以下三项保持在同一目录：

```text
HaitooHubAgent.app                 日常菜单栏入口
HaitooHubAgentConsole/             给启动脚本使用的可见终端程序目录
启动并配对.command                  首次安装与排错入口
```

内部测试可暂不签名和公证，员工应使用 `启动并配对.command`。正式外部分发前，需使用 Apple Developer ID 对 `.app` 签名并公证，并对控制台程序目录中的可执行文件签名；之后可将 `HaitooHubAgent.app` 安装至 `/Applications`。

日常常驻运行使用当前用户的 LaunchAgent。将 `install/macos/com.haitoo.hub-agent.plist` 的程序路径替换为实际安装路径后，执行：

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.haitoo.hub-agent.plist
```

## Windows 构建与分发

必须在 Windows 上构建：

```powershell
cd hub_agent
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

`dist\` 会包含 `HaitooHubAgent.exe`、`HaitooHubAgentConsole\` 和 `启动并配对.cmd`。首次安装时请保留它们的相对位置。正式发布前，对 EXE 和安装包进行代码签名，并使用 Inno Setup 或 WiX 制作安装程序。

安装完成后，以员工当前账号执行：

```powershell
.\install\windows\install-startup.ps1
```

脚本创建“用户登录时”启动的计划任务。不可改用 Windows Service，否则无法可靠控制员工桌面会话中的 HubStudio 浏览器。

## 开发排错命令

仅在开发时使用：

```bash
/Users/rock/codespace/haitoo-erp/.venv/bin/python -m pip install -r requirements.txt
/Users/rock/codespace/haitoo-erp/.venv/bin/python haitoo_hub_agent.py console
/Users/rock/codespace/haitoo-erp/.venv/bin/python haitoo_hub_agent.py tray
```

`console` 与 `tray` 共用本机工作页和后台执行流程；`console` 同时显示终端日志，`tray` 用于日常菜单栏运行。暂停只停止领取新任务，不取消当前执行。旧版 `register --user-token` 仅保留给兼容性排错，不是员工安装流程。

## 同步与任务行为

- 使用 HubStudio 当前客户端登录态和当前团队，调用 Local API；不会拿公司凭据重新登录或切换团队。公司凭据仍在 ERP 配置页加密保存，浏览器不能读取。
- 官方环境列表契约：[获取环境列表](https://api-docs.hubstudio.cn/380052376e0)，`POST /api/v1/env/list`，分页字段 `current` / `size`，返回 `data.list` / `data.total`。文档明确“用户仅能查询自己有权限的环境信息”。必须全部分页成功才向 ERP 更新访问快照。
- 官方启动契约：[打开环境](https://api-docs.hubstudio.cn/380052361e0)，`POST /api/v1/browser/start`，使用环境 `containerCode` 和布尔参数，返回 `debuggingPort`。环境名、分组、序号、标签按接口实际返回展示；代理密码、平台账号和 IP 不同步到 ERP。
- 本账号可使用多台电脑。同环境同时只运行一个任务；每次领取生成独立凭证和执行尝试。失联或异常不自动重试，历史日志不会被覆盖。
- 重试前必须核对平台，重试复用原 XLSX。运行中不能取消；待处理任务阻止同环境下一项执行。人工确认记录账号与时间。
- 自动提交只接受明确的成功提示。当前提交页面和文案适配仍需在实际 TikTok 本土店环境验收；未知页面会进入人工处理，不猜测点击。

## 开发验证

在项目根目录执行：

```bash
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p 'test_hubstudio_tasks.py'
PYTHONPATH=backend .venv/bin/python -m unittest discover -s backend/tests -p 'test_schema_migrations.py'
.venv/bin/python -m unittest discover -s hub_agent/tests
npm run build --prefix frontend
```

本机网页测试会临时监听回环测试端口，不连接生产 ERP、HubStudio 或 TikTok。`HAITOO_AGENT_DATA_DIR` 可指定开发/测试配置和日志目录；不设置时保持系统默认目录。打包脚本将工作页静态资源包含在程序内，Mac 和 Windows 分别在对应系统构建。

## 领取协议与升级

新版使用 `X-Hub-Protocol: 3`，领取时只提交本机已启用环境的 ID、名称和本土确认；数据库将其记入本次任务与执行尝试，保留运行锁防止多电脑同时执行同环境。未选择环境、快照过期或已选环境不在当前完整列表中时，不请求领取。ERP 创建任务不依赖环境列表；任务记录、日志和执行尝试仍由 ERP 数据库保存。环境上传接口返回 410，旧协议返回 426。

升级前退出旧执行器，后端迁移至 `20261007_30`，同步发布前端并重新打包执行器。旧活动任务必须先核对平台结果；重试时复用原 XLSX，由领取电脑当前选择的环境执行，历史尝试保留原目标。

### 自动上品 Excel 的 R2 存储

新版任务将固定 XLSX 上传到独立私有 R2 桶。数据库保存 `export_url`、文件大小、SHA-256 和 7 天有效期，新的 `export_blob` 为空；历史数据库文件继续可读。数据库中的链接是私有对象地址，执行器通过 ERP 的鉴权下载接口取文件，不使用图片公网域名。

部署前，在对应环境文件中添加 `R2_HUB_EXPORT_BUCKET=<私有桶名>`，已有 R2 endpoint 和访问密钥继续使用，密钥需具备该桶读写和删除权限。桶保持私有，禁止启用公网访问。在 Cloudflare R2 生命周期设置中新增仅匹配 `hub-exports/` 前缀的 7 天删除规则，保留其他规则；该规则同时清理服务停机期间过期文件及意外遗留对象。API 每分钟删除数据库关联的过期文件，失败会重试。任务和日志不随文件删除。

本机部署（保留 `.env.local` 和数据库卷）：

```bash
./deploy/local.sh build api migrate submit-worker result-worker miaoshou-collect-box-worker product-library-rankings-worker
./deploy/local.sh run --rm migrate
./deploy/local.sh up -d api submit-worker result-worker miaoshou-collect-box-worker product-library-rankings-worker
```

腾讯云部署（保留 `.env` 和数据库卷，先按项目运维流程备份数据库）：

```bash
./deploy/tencent.sh build api migrate submit-worker result-worker miaoshou-collect-box-worker product-library-rankings-worker
./deploy/tencent.sh run --rm migrate
./deploy/tencent.sh up -d api submit-worker result-worker miaoshou-collect-box-worker product-library-rankings-worker
./deploy/tencent.sh exec edge nginx -t
./deploy/tencent.sh exec edge nginx -s reload
```

数据库需迁移至 `20261007_30`。升级时同步重建其他后端 worker，避免旧容器继续使用旧模型。文件超时后禁止下载、领取和重试，排队任务显示“文件已过期”，需要重新生成。已提交或待人工处理的任务保留原状态；人工确认仍可用于记录已核对的平台结果。
