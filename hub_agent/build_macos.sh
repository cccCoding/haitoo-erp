#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_PYTHON="$(pwd)/../.venv/bin/python"
if [[ ! -x "$PROJECT_PYTHON" ]]; then
  echo "未找到项目 .venv/bin/python，请先准备项目虚拟环境。" >&2
  exit 1
fi
"$PROJECT_PYTHON" -m PyInstaller --noconfirm --windowed --add-data "trusted_keys.json:." --add-data "agent-version.json:." --name HaitooHubAgent haitoo_hub_agent.py
"$PROJECT_PYTHON" -m PyInstaller --noconfirm --console --add-data "trusted_keys.json:." --add-data "agent-version.json:." --name HaitooHubAgentConsole haitoo_hub_agent.py
cp start_and_pair_macos.command dist/启动并配对.command
chmod +x dist/启动并配对.command

AGENT_VERSION="$("$PROJECT_PYTHON" -c 'import json; print(json.load(open("agent-version.json"))["version"])')"
AGENT_ARCH="$("$PROJECT_PYTHON" -c 'import platform; print("arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64")')"
ARCHIVE_DIRECTORY="$(mktemp -d "${TMPDIR:-/tmp}/haitoo-connector-package.XXXXXX")"
trap 'rm -rf "$ARCHIVE_DIRECTORY"' EXIT
DOWNLOAD_NAME="HaitooHubAgent-macos-$AGENT_ARCH-$AGENT_VERSION.zip"
(
  cd dist
  zip -qry "$ARCHIVE_DIRECTORY/$DOWNLOAD_NAME" HaitooHubAgent.app HaitooHubAgentConsole 启动并配对.command
)
mv "$ARCHIVE_DIRECTORY/$DOWNLOAD_NAME" "dist/$DOWNLOAD_NAME"
echo "网页下载包：$(pwd)/dist/$DOWNLOAD_NAME"

echo "已生成：$(pwd)/dist/HaitooHubAgent.app"
echo "首次安装/排错入口：$(pwd)/dist/启动并配对.command"
echo "未签名内部测试请让员工双击“启动并配对.command”；发布前请使用 Apple Developer ID 对该 .app 签名并公证。"
