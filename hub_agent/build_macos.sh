#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
python3 -m venv .build-venv
.build-venv/bin/python -m pip install --upgrade pip
.build-venv/bin/python -m pip install -r requirements.txt
.build-venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name HaitooHubAgent haitoo_hub_agent.py
.build-venv/bin/python -m PyInstaller --noconfirm --clean --console --name HaitooHubAgentConsole haitoo_hub_agent.py
cp start_and_pair_macos.command dist/启动并配对.command
chmod +x dist/启动并配对.command

echo "已生成：$(pwd)/dist/HaitooHubAgent.app"
echo "首次安装/排错入口：$(pwd)/dist/启动并配对.command"
echo "未签名内部测试请让员工双击“启动并配对.command”；发布前请使用 Apple Developer ID 对该 .app 签名并公证。"
