@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
if not exist "HaitooHubAgentConsole\HaitooHubAgentConsole.exe" (
  echo 未找到 HaitooHubAgentConsole。请保留完整解压目录。
  pause
  exit /b 1
)
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 45679 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if %errorlevel%==0 (
  echo 连接器端口 45679 已被占用。如需重启，请先退出已有连接器。
  echo 设备、环境和任务请在 ERP 的 TK 矩阵页面查看。
  pause
  exit /b 0
)
echo 正在启动 Haitoo Hub 连接器；首次启动将打开 ERP 矩阵页面进行授权。
echo 关闭这个窗口 = 停止连接器。
"HaitooHubAgentConsole\HaitooHubAgentConsole.exe" console
set EXIT_CODE=%errorlevel%
echo 启动进程已退出，退出码：%EXIT_CODE%。自动更新时，新进程可能仍在运行，请在 ERP 查看设备状态。
echo 日志位置："%LOCALAPPDATA%\HaitooHubAgent\agent.log"
pause
exit /b %EXIT_CODE%
