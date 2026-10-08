# Haitoo HubStudio 本地执行器

此执行器安装在员工电脑上，以安装 HubStudio 的当前桌面用户运行。ERP 保存账号任务和固定 XLSX；执行器只在本机内存同步当前可访问环境，原子领取本账号任务，在对应 HubStudio 环境内完成 TikTok 批量上传和导入。环境无需管理员创建店铺、分配人员或绑定电脑。

它不是 Windows Service，也不能部署到 ERP 服务器。

## 部署前提

在首次运行本地执行器前，生产 ERP 必须已经发布包含 Hub 执行器接口的后端，并已执行迁移至 `20261007_30`。本地登录使用现有 `/auth/login` 和 `/hub-agents/register` 接口；若返回 HTTP 404，需检查 API 地址和服务器发布版本。

## 使用方式与安全边界

- 执行器默认请求 `https://api.haitorok.com`。首次启动在本地工作页输入 ERP 邮箱和密码，点击“登录并授权”，由本地程序调用 ERP 登录和电脑注册接口；密码及 ERP 登录 Token 不保存、不返回页面，系统凭据库只保存执行器 Token。腾讯云使用其他域名时，通过 `HAITOO_API_URL` 指定 HTTPS API 地址；显式配置会覆盖本机保存的旧 API 地址。已有电脑授权继续沿用，失效后重新显示登录表单。已授权时不提供切换账号，避免执行中的任务改变身份。
- 终端名称自动取电脑名称并附加短标识，避免同名电脑注册冲突；终端令牌仅保存到 macOS Keychain 或 Windows Credential Manager，不写入配置文件。
- 执行器提供本机工作页 `http://127.0.0.1:45679`，不监听局域网。工作页包含环境列表、本账号任务、执行尝试、日志和人工处理；浏览器不持有执行器 Token 或公司 Secret。页面关闭后执行器仍继续工作。
- 环境列表“账号”列显示该环境绑定的账号，无账号显示 `-`，多个账号同时展示；仅账号名称进入本机环境快照，密码及密钥仍不返回工作页。顶部仅保留暂停领取按钮；执行中的任务在操作列显示“停止”，仅执行此任务的本机可点击。“查看日志”通过弹窗展示任务详情、每次执行日志，支持关闭按钮、Esc 和点击遮罩关闭。环境列表不显示标签，自动上品按钮使用绿色“已开启”和红色“已关闭”。任务列表不显示执行电脑，创建时间紧邻目标环境右侧；重试、确认已提交和取消任务按任务状态显示在操作列，仍要求核对平台后确认操作。任务框固定 420px（窄屏 400px），运行日志框固定 320px，内容在框内滚动；运行日志可复制或清除，清除仅清空本机日志文件，不删除 ERP 任务记录，后续新日志继续显示。
- TikTok 登录状态保留在 HubStudio 指纹环境内。ERP 不下发 TikTok 账号密码。进入登录页时，任务显示“等待 TikTok 登录”，执行器将页面置前，最多等待 10 分钟；员工在该页面完成登录及验证后自动继续原任务。等待期间不上传、不提交，心跳继续维持任务租约。超时或页面校验失败进入人工处理，保留页面供核对。
- 领取后通过 Local API 的 `/api/v1/env/list` 按 `containerCodes` 查询当前环境绑定账号，再调用 `/api/v1/account/list` 按账号与名称查询并精确匹配。只允许唯一账号，不读取全公司凭据作为缓存。账号、密码和 2FA 密钥仅保留在本次执行的内存对象中，不写配置、工作页接口或 ERP；日志只记录“本次 1/1 个账号有密码”等可用数量。读取密码需要 HubStudio 当前用户具备“团队设置-编辑-环境-我的账号-密码查看”权限，否则密码返回空，继续等待人工登录。
- 马来西亚店铺使用已确认的上传地址 `https://seller-my.tiktok.com/product/batch/publish?entry-from=hub&shop_region=MY&step=2`，登录完成后仍返回该完整地址。其他绑定域名暂沿用旧路径，需要对应站点实际验收。ERP 创建任务和执行器上传前均检查 20 MB 上限，执行器只接受 `.xlsx`。登录页只识别当前语言，不切换：简体中文使用“使用邮箱登录”入口，US English / UK English 使用“Log in with email”入口。登录完成并返回上传页后，打开右上角账号菜单，检查并切换为简体中文，再关闭菜单后上传；已登录的环境也执行此检查。菜单入口、切换结果或关闭状态无法确认时转人工处理，尚未上传。切换语言后最多用 30 秒核对账号菜单中的简体中文；页面刷新导致菜单关闭时会重新打开核对，而非只点击一次后等待。任务详情与本机日志同步记录登录成功、检查语言、当前语言、切换开始/结果、关闭账号菜单、开始上传和等待解析；失败记录具体操作步骤。菜单关闭检查兼容退出登录行中同时显示邮箱的情况，避免重复点击把菜单关掉后仍等待语言项。检测到登录页后最多尝试一次邮箱密码登录：先识别是否已有可见邮箱表单；没有时点击“使用邮箱登录”，等待邮箱表单可见后再填入环境绑定的邮箱和密码。只有唯一明确表单才能填写。验证码、2FA、手机号登录及未知表单交给人工处理，不反复提交登录。登录仅定位可见输入框，切换后等待邮箱与密码表单各最多 30 秒；点击登录自动等待按钮启用。失败日志记录具体步骤和异常类型，不记录原始错误、表单内容或密码。当前已确认第 2 步上传页以及“导入成功”完成提示；未知控件不自动点击。

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

`dist\` 会包含 `HaitooHubAgent\HaitooHubAgent.exe`、`HaitooHubAgentConsole\HaitooHubAgentConsole.exe` 和 `启动并配对.cmd`。首次安装时请保留两个完整程序目录及启动脚本的相对位置，不能只复制 EXE。正式发布前，对 EXE 和安装包进行代码签名，并使用 Inno Setup 或 WiX 制作安装程序。

没有 Windows 电脑时，可使用仓库中的 `.github/workflows/hub-agent-windows.yml`：将代码提交并推送到 GitHub 默认分支，在仓库 Actions 中选择“构建 Windows 本地执行器”，点击 Run workflow，并选择要构建的分支。工作流使用 Windows x64 runner 和 Python 3.12，先运行执行器单元测试，再生成两个程序目录并检查工作页静态资源，最后上传完整安装包。失败的测试或打包步骤会中止构建。

运行成功后，在该次运行页面的 Artifacts 下载 `HaitooHubAgent-Windows-x64-运行编号`，完整解压后双击 `启动并配对.cmd`。无需配置 GitHub Secrets，也不会打入本机登录令牌。产物保留 14 天；云端构建只验证测试和打包，HubStudio 启动、邮箱登录及实际导入仍需在员工 Windows 电脑上验收。

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

本机工作页任务操作列为执行中的任务提供“停止”，仅在此电脑正在执行该任务时可用。确认后取消本机执行协程并暂停领取新任务，保留 HubStudio 浏览器页面；任务记录“人工中止”并转为待人工处理，继续保留环境锁。尚未进入导入阶段与可能已经点击导入分别提示；平台已经收到的文件或导入无法通过本机中止撤回。核对平台后可确认已提交、核对后重试或取消任务，再点击“继续领取”。如果中止报告因网络故障未送达，任务会在租约超时后进入人工处理。此功能不修改后端运行中任务的取消接口，也不能中止其他电脑上的任务。

日志先显示“检查 TikTok 登录”，确认上传控件就绪后才显示“上传表格”。登录重定向中断页面导航时会转入登录等待；其他 Playwright 错误在本机日志记录原始堆栈，ERP 仅保存通用提示和异常类型所在的本机日志可用于定位。排错时不要公开原始日志中可能包含的页面及请求信息。

马来西亚第 2 步上传 XLSX 后，先等待本次文件名可见以及正数“款商品准备就绪”提示（各最多 120 秒），再确认唯一可用的“导入”按钮。排除已有的可见导入成功提示并写入“导入商品”日志后点击一次，最多等待 60 秒出现包含“导入成功”的可见文字（不限制商品数量或整句格式），随后记为完成（阶段 imported / 导入成功），不再点击提交或发布按钮。“上传成功”“准备就绪”不作为任务完成依据；导入后结果不明确时转人工核对，避免重复导入。

从文件交给上传页后开始，在等待文件名、商品准备就绪、导入按钮及导入结果期间持续检测可见的“出错商品”/“出错的商品”提示。检测覆盖主页面中的弹窗、可见 iframe 和由当前页面打开的独立弹窗；不检查其他无关页面。点击导入后同时等待成功或数据错误。出现数据错误编辑器时立即记为失败（阶段 import_data_error），原因“上传成功，添加商品失败（数据错误）；请人工查看 TikTok 在线编辑器中的出错商品并处理”，保留浏览器页面供人工处理，不继续点击导入或发布，也不记为成功。数据错误任务不显示重试按钮，接口也拒绝重试；请人工查看错误并修正数据后创建新任务。隐藏的错误提示不触发失败；同时有成功和出错商品时按数据错误失败处理。

等待文件、解析结果及导入按钮期间持续检查可见的“此文件已存在”提示。出现时立即停止，不点击导入或发布，任务标记“失败 / 文件已存在，已中止”，并暂停本机领取新任务。提示员工上传其他文件或查看上传记录核对已有结果，不自动重试、不自动重命名绕过平台重复校验；核对平台后再进行人工处理和恢复领取。

## 同步与任务行为

- 使用 HubStudio 当前客户端登录态和当前团队，调用 Local API；不会拿公司凭据重新登录或切换团队。公司凭据仍在 ERP 配置页加密保存，浏览器不能读取。
- 官方环境列表契约：[获取环境列表](https://api-docs.hubstudio.cn/380052376e0)，`POST /api/v1/env/list`，分页字段 `current` / `size`，返回 `data.list` / `data.total`。文档明确“用户仅能查询自己有权限的环境信息”。必须全部分页成功才向 ERP 更新访问快照。
- 官方启动契约：[打开环境](https://api-docs.hubstudio.cn/380052361e0)，`POST /api/v1/browser/start`，使用环境 `containerCode` 和布尔参数，返回 `debuggingPort`。环境名、分组、序号、标签按接口实际返回展示；代理密码、平台账号和 IP 不同步到 ERP。
- 本账号可使用多台电脑。同环境同时只运行一个任务；每次领取生成独立凭证和执行尝试。失联或异常不自动重试，历史日志不会被覆盖。
- 重试前必须核对平台，重试复用原 XLSX。运行中不能取消；待处理任务阻止同环境下一项执行。人工确认记录账号与时间。
- 自动导入只接受明确的“导入成功”提示；未知页面会进入人工处理，不猜测点击。

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
