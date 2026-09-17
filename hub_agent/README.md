# Haitoo HubStudio 本地执行器

此执行器安装在员工电脑上，以安装 HubStudio 的当前桌面用户运行。ERP 云端只负责分配任务；执行器在本机启动指定 HubStudio 环境，并在该环境内完成 TikTok 批量上品。

它不是 Windows Service，也不能部署到 ERP 服务器。

## 部署前提

在首次运行本地执行器前，生产 ERP 必须已经发布包含 Hub 执行器接口的后端，并已执行迁移至 `20260917_08`。否则本地执行器会提示 `/hub-agent/pairings` 不存在（HTTP 404）；这表示服务器版本未更新，不是账号或授权失败。

## 使用方式与安全边界

- 执行器请求固定 API 地址 `https://api.haitoro.com`；首次授权时会打开 ERP 登录页 `https://erp.haitoro.com`。员工直接使用已有 ERP 账号密码登录并授权当前电脑，无需复制登录 Token。
- 终端名称自动取电脑名称；终端令牌仅保存到 macOS Keychain 或 Windows Credential Manager，不写入配置文件。
- 执行器只提供本机状态页 `http://127.0.0.1:45679`，不监听局域网，不能被同一 Wi-Fi 的其它电脑访问。
- TikTok 登录状态保留在 HubStudio 指纹环境内。ERP 不下发 TikTok 账号密码；若登录失效、验证码或页面校验失败，任务会进入人工处理。

## 给员工的首次启动说明

未签名的内部测试包请优先双击 **启动并配对**，不要直接双击 App：

- macOS：双击 `启动并配对.command`。它会清除当前安装包的下载隔离标记、在 Terminal 显示运行日志，并在状态页可用后打开浏览器。
- Windows：双击 `启动并配对.cmd`。它会保留命令窗口显示错误，并在状态页可用后打开浏览器。

终端窗口不可关闭；关闭它等同于停止执行器。首次启动后，在浏览器中登录 ERP 并确认授权即可。状态页会依次显示授权、等待任务、启动 HubStudio、上传 XLSX、提交或“需要人工处理”等阶段；显示“在线，等待任务”后，管理员可在 ERP 分配已绑定店铺的上品任务。

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
pip install -r requirements.txt
python haitoo_hub_agent.py console
python haitoo_hub_agent.py tray
```

`console` 用于显示日志和本机状态页；`tray` 用于日常无终端窗口的菜单栏模式。旧版 `register --user-token` 仅保留给兼容性排错，不是员工安装流程。
