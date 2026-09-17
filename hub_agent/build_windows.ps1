$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

py -3 -m venv .build-venv
& .\.build-venv\Scripts\python.exe -m pip install --upgrade pip
& .\.build-venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name HaitooHubAgent haitoo_hub_agent.py
& .\.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --console --name HaitooHubAgentConsole haitoo_hub_agent.py
Copy-Item .\start_and_pair_windows.cmd .\dist\启动并配对.cmd

Write-Host "已生成：$PSScriptRoot\dist\HaitooHubAgent.exe"
Write-Host "首次安装/排错入口：$PSScriptRoot\dist\启动并配对.cmd"
Write-Host "发布前请使用代码签名证书签名，并用 Inno Setup/WiX 制作安装包。"
