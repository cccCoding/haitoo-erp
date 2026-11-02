param(
    [string]$PythonExecutable = "",
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($PythonExecutable) {
    & $PythonExecutable -m venv .build-venv
} else {
    py -3 -m venv .build-venv
}
if ($LASTEXITCODE -ne 0) { throw "创建构建虚拟环境失败" }

function Invoke-BuildPython {
    param([string[]]$PythonArguments)
    & .\.build-venv\Scripts\python.exe @PythonArguments
    if ($LASTEXITCODE -ne 0) { throw "Python 构建步骤失败（退出码：$LASTEXITCODE）" }
}

Invoke-BuildPython -PythonArguments @("-m", "pip", "install", "--upgrade", "pip")
Invoke-BuildPython -PythonArguments @("-m", "pip", "install", "-r", "requirements.txt")
if ($RunTests) {
    Invoke-BuildPython -PythonArguments @("-m", "unittest", "discover", "-s", "tests")
}
Invoke-BuildPython -PythonArguments @("-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--add-data", "trusted_keys.json;.", "--add-data", "agent-version.json;.", "--name", "HaitooHubAgent", "haitoo_hub_agent.py")
Invoke-BuildPython -PythonArguments @("-m", "PyInstaller", "--noconfirm", "--clean", "--console", "--add-data", "trusted_keys.json;.", "--add-data", "agent-version.json;.", "--name", "HaitooHubAgentConsole", "haitoo_hub_agent.py")
Copy-Item .\start_and_pair_windows.cmd .\dist\启动并配对.cmd

foreach ($required in @("HaitooHubAgent\HaitooHubAgent.exe", "HaitooHubAgentConsole\HaitooHubAgentConsole.exe", "启动并配对.cmd")) {
    if (-not (Test-Path (Join-Path "$PSScriptRoot\dist" $required))) {
        throw "安装包缺少必要文件：$required"
    }
}

Write-Host "已生成：$PSScriptRoot\dist\HaitooHubAgent\HaitooHubAgent.exe"
Write-Host "首次安装/排错入口：$PSScriptRoot\dist\启动并配对.cmd"
Write-Host "发布前请使用代码签名证书签名，并用 Inno Setup/WiX 制作安装包。"

$agentVersion = (Get-Content .\agent-version.json -Raw | ConvertFrom-Json).version
$agentArch = & .\.build-venv\Scripts\python.exe -c "import platform; print('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64')"
if ($LASTEXITCODE -ne 0) { throw "无法确认构建架构" }
$downloadZip = Join-Path "$PSScriptRoot\dist" "HaitooHubAgent-windows-$agentArch-$agentVersion.zip"
Compress-Archive -Path @(".\dist\HaitooHubAgent", ".\dist\HaitooHubAgentConsole", ".\dist\启动并配对.cmd") -DestinationPath $downloadZip -Force
Write-Host "网页下载包：$downloadZip"
