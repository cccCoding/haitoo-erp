@echo off
setlocal
cd /d "%~dp0"

if not exist "HaitooHubAgentConsole\HaitooHubAgentConsole.exe" (
  echo 未找到 HaitooHubAgentConsole。请确认“启动并配对.cmd”与程序目录位于同一位置。
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 45679 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  echo Haitoo Hub 执行器似乎已经运行。
  start "" "http://127.0.0.1:45679"
  pause
  exit /b 0
)

echo 正在启动 Haitoo Hub 执行器...
echo 状态页：http://127.0.0.1:45679
echo 关闭这个窗口 = 停止执行器。
start "Haitoo Hub 状态页" /b powershell -NoProfile -Command "for ($i=0; $i -lt 60; $i++) { try { Invoke-WebRequest http://127.0.0.1:45679/health -UseBasicParsing -TimeoutSec 1 ^| Out-Null; Start-Process http://127.0.0.1:45679; break } catch {}; Start-Sleep -Seconds 1 }"

"HaitooHubAgentConsole\HaitooHubAgentConsole.exe" console
set EXIT_CODE=%errorlevel%
echo.
echo 执行器已停止（退出码：%EXIT_CODE%）。
echo 日志位置：%%USERPROFILE%%\AppData\Local\HaitooHubAgent\agent.log
pause
exit /b %EXIT_CODE%
