#!/usr/bin/env bash
# 未签名内部测试的可见启动入口：所有状态与错误保留在此终端窗口。
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_PATH="$SCRIPT_DIR/$(basename "$0")"
cd "$SCRIPT_DIR" || exit 1

CONSOLE_APP="HaitooHubAgentConsole/HaitooHubAgentConsole"
if [[ ! -f "$CONSOLE_APP" ]]; then
  echo "未找到 HaitooHubAgentConsole。请确认“启动并配对.command”与程序目录位于同一目录。"
  read -r -p "按回车键关闭..."
  exit 1
fi

# 内部下载包可能带有 Gatekeeper 隔离标记；只处理当前安装包，不触及其它文件。
xattr -dr com.apple.quarantine "$SCRIPT_DIR/HaitooHubAgentConsole" "$SCRIPT_DIR/HaitooHubAgent.app" "$LAUNCHER_PATH" 2>/dev/null || true
chmod +x "$CONSOLE_APP" "$LAUNCHER_PATH"

if lsof -nP -iTCP:45679 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Haitoo Hub 执行器似乎已经在运行（本机状态页端口 45679 已被占用）。"
  echo "请打开 http://127.0.0.1:45679 查看状态；如需重启，请先退出已有执行器。"
  read -r -p "按回车键关闭..."
  exit 0
fi

echo "正在启动 Haitoo Hub 执行器..."
echo "状态页就绪后会自动打开：http://127.0.0.1:45679"
echo "关闭这个终端窗口 = 停止执行器。"

(
  for _ in {1..60}; do
    if curl --silent --fail --max-time 1 http://127.0.0.1:45679/health >/dev/null 2>&1; then
      open "http://127.0.0.1:45679"
      exit 0
    fi
    sleep 1
  done
) &

if "$CONSOLE_APP" console; then
  echo
  echo "执行器已停止。"
else
  echo
  echo "执行器因错误停止，请根据上方提示处理。"
fi
echo
echo "日志位置：$HOME/Library/Logs/HaitooHubAgent/agent.log"
read -r -p "请截图以上错误信息后，按回车键关闭..."
exit 0
