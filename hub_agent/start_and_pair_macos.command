#!/usr/bin/env bash
# 未签名内部测试的可见启动入口：连接状态与错误保留在终端。
set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER_PATH="$SCRIPT_DIR/$(basename "$0")"
cd "$SCRIPT_DIR" || exit 1
CONSOLE_APP="HaitooHubAgentConsole/HaitooHubAgentConsole"
if [[ ! -f "$CONSOLE_APP" ]]; then
  echo "未找到 HaitooHubAgentConsole。请保留完整解压目录。"
  read -r -p "按回车键关闭..."
  exit 1
fi
chmod +x "$CONSOLE_APP" "$LAUNCHER_PATH"
if lsof -nP -iTCP:45679 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "连接器端口 45679 已被占用。如需重启，请先退出已有连接器。"
  echo "设备、环境和任务请在 ERP 的 TK 矩阵页面查看。"
  read -r -p "按回车键关闭..."
  exit 0
fi
echo "正在启动 Haitoo Hub 连接器；首次启动将打开 ERP 矩阵页面进行授权。"
echo "关闭这个终端窗口 = 停止连接器。"
echo "若系统拒绝运行，请查看“系统设置 → 隐私与安全性”中的实际提示，或在 ERP 查看手动安装指导。"
"$CONSOLE_APP" console
CONNECTOR_EXIT=$?
echo "连接器已停止（退出码：$CONNECTOR_EXIT）。"
echo "日志位置：$HOME/Library/Logs/HaitooHubAgent/agent.log"
read -r -p "按回车键关闭..."
exit "$CONNECTOR_EXIT"
