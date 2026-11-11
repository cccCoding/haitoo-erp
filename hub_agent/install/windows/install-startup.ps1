param([string]$Binary = "")
$ErrorActionPreference = "Stop"
if (-not $Binary) { $Binary = Join-Path $env:LOCALAPPDATA 'Programs\HaitooHubAgent\HaitooHubAgent\HaitooHubAgent.exe' }
if (-not (Test-Path -LiteralPath $Binary)) { throw "请先安装正式连接器：$Binary" }
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
New-Item -Path $runKey -Force | Out-Null
New-ItemProperty -Path $runKey -Name HaitooHubAgent -PropertyType String -Value ('"' + $Binary + '" tray') -Force | Out-Null
# 仅移除旧版本明确命名的当前用户任务，避免与新入口重复启动。
$task = Get-ScheduledTask -TaskName HaitooHubAgent -ErrorAction SilentlyContinue
if ($task -and $task.Principal.UserId -in @($env:USERNAME, "$env:USERDOMAIN\$env:USERNAME")) {
    Unregister-ScheduledTask -TaskName HaitooHubAgent -Confirm:$false
}
