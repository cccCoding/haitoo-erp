param(
    [string]$PythonExecutable = "",
    [switch]$RunTests,
    [switch]$Release,
    [switch]$InternalRelease
)

$ErrorActionPreference = "Stop"
if ($Release -and $InternalRelease) { throw '不能同时选择正式签名与内部发布模式' }
if ($Release -or $InternalRelease) {
    foreach ($name in @('HAITOO_RELEASE_PRIVATE_KEY', 'HAITOO_RELEASE_KEY_ID')) {
        if (-not [Environment]::GetEnvironmentVariable($name)) { throw "正式构建缺少环境变量 $name" }
    }
    if (-not (Get-Content (Join-Path $PSScriptRoot 'trusted_keys.json') -Raw | ConvertFrom-Json).PSObject.Properties.Count) { throw '发布构建必须内置公司的更新公钥' }
}
if ($Release -and -not $env:HAITOO_WINDOWS_CERT_SHA1) { throw '正式签名构建缺少 HAITOO_WINDOWS_CERT_SHA1' }
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
$metadataDirectory = Join-Path ([IO.Path]::GetTempPath()) ("haitoo-agent-build-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $metadataDirectory | Out-Null
$metadataPath = Join-Path $metadataDirectory 'agent-version.json'
$metadata = Get-Content .\agent-version.json -Raw | ConvertFrom-Json
$metadata | Add-Member -NotePropertyName distribution -NotePropertyValue $(if ($Release) { 'signed' } else { 'internal' }) -Force
[IO.File]::WriteAllText($metadataPath, ($metadata | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
try {
Invoke-BuildPython -PythonArguments @("-m", "PyInstaller", "--noconfirm", "--windowed", "--add-data", "trusted_keys.json;.", "--add-data", "${metadataPath};.", "--name", "HaitooHubAgent", "haitoo_hub_agent.py")
Invoke-BuildPython -PythonArguments @("-m", "PyInstaller", "--noconfirm", "--console", "--add-data", "trusted_keys.json;.", "--add-data", "${metadataPath};.", "--name", "HaitooHubAgentConsole", "haitoo_hub_agent.py")
Copy-Item .\start_and_pair_windows.cmd .\dist\启动并配对.cmd

foreach ($required in @("HaitooHubAgent\HaitooHubAgent.exe", "HaitooHubAgentConsole\HaitooHubAgentConsole.exe", "启动并配对.cmd")) {
    if (-not (Test-Path (Join-Path "$PSScriptRoot\dist" $required))) {
        throw "安装包缺少必要文件：$required"
    }
}

Write-Host "已生成：$PSScriptRoot\dist\HaitooHubAgent\HaitooHubAgent.exe"
Write-Host "首次安装/排错入口：$PSScriptRoot\dist\启动并配对.cmd"
if ($InternalRelease) { Write-Host "内部发布使用公司更新签名，不需要 Windows 商业代码签名证书。" } else { Write-Host "正式发布请使用 -Release 完成代码签名与安装器构建。" }

$agentVersion = (Get-Content .\agent-version.json -Raw | ConvertFrom-Json).version
$agentArch = & .\.build-venv\Scripts\python.exe -c "import platform; print('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64')"
if ($LASTEXITCODE -ne 0) { throw "无法确认构建架构" }
$downloadZip = Join-Path "$PSScriptRoot\dist" "HaitooHubAgent-windows-$agentArch-$agentVersion.zip"
Compress-Archive -Path @(".\dist\HaitooHubAgent", ".\dist\HaitooHubAgentConsole", ".\dist\启动并配对.cmd") -DestinationPath $downloadZip -Force
Write-Host "网页下载包：$downloadZip"

if ($Release) {
    if ($agentArch -ne 'x64') { throw '当前正式 Windows 仅支持 x64' }
    $signTool = if ($env:SIGNTOOL_EXE) { $env:SIGNTOOL_EXE } else { 'signtool.exe' }
    $iscc = if ($env:ISCC_EXE) { $env:ISCC_EXE } else { 'ISCC.exe' }
    foreach ($binary in @('.\dist\HaitooHubAgent\HaitooHubAgent.exe', '.\dist\HaitooHubAgentConsole\HaitooHubAgentConsole.exe')) {
        & $signTool sign /sha1 $env:HAITOO_WINDOWS_CERT_SHA1 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $binary
        if ($LASTEXITCODE -ne 0) { throw 'Windows 程序签名失败' }
        & $signTool verify /pa $binary
        if ($LASTEXITCODE -ne 0) { throw 'Windows 签名验证失败' }
    }
    & $iscc "/DAgentVersion=$agentVersion" '.\install\windows\installer.iss'
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup 安装包构建失败' }
    $baseName = "HaitooHubAgent-windows-x64-$agentVersion"
    $installer = "dist/$baseName.exe"
    & $signTool sign /sha1 $env:HAITOO_WINDOWS_CERT_SHA1 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $installer
    if ($LASTEXITCODE -ne 0) { throw '安装包签名失败' }
    & $signTool verify /pa $installer
    if ($LASTEXITCODE -ne 0) { throw '安装包签名验证失败' }
    Invoke-BuildPython -PythonArguments @('package_release.py', '--source', 'dist/HaitooHubAgent', '--output', "dist/$baseName-update.zip")
    Invoke-BuildPython -PythonArguments @('sign_release.py', '--package', "dist/$baseName-update.zip", '--installer', $installer, '--key', $env:HAITOO_RELEASE_PRIVATE_KEY, '--key-id', $env:HAITOO_RELEASE_KEY_ID, '--version', $agentVersion, '--platform', 'windows', '--arch', 'x64', '--kind', 'agent', '--entrypoint', 'HaitooHubAgent/HaitooHubAgent.exe', '--output', "dist/$baseName-manifest.json")
    Write-Host "正式产物：$installer、$baseName-update.zip、$baseName-manifest.json"
}

if ($InternalRelease) {
    if ($agentArch -ne 'x64') { throw '当前 Windows 内部发布仅支持 x64' }
    $baseName = "HaitooHubAgent-windows-x64-$agentVersion"
    Invoke-BuildPython -PythonArguments @('package_release.py', '--source', 'dist/HaitooHubAgent', '--output', "dist/$baseName-update.zip")
    Invoke-BuildPython -PythonArguments @('sign_release.py', '--distribution', 'internal', '--package', "dist/$baseName-update.zip", '--installer', $downloadZip, '--key', $env:HAITOO_RELEASE_PRIVATE_KEY, '--key-id', $env:HAITOO_RELEASE_KEY_ID, '--version', $agentVersion, '--platform', 'windows', '--arch', 'x64', '--kind', 'agent', '--entrypoint', 'HaitooHubAgent/HaitooHubAgent.exe', '--output', "dist/$baseName-manifest.json")
    Write-Host "内部发布产物：$baseName.zip、$baseName-update.zip、$baseName-manifest.json；程序未使用 Windows 商业证书签名。"
}
} finally {
    Remove-Item -LiteralPath $metadataDirectory -Recurse -Force -ErrorAction SilentlyContinue
}
