$taskName = "HaitooHubAgent"
$binary = Join-Path $PSScriptRoot "..\..\dist\HaitooHubAgent.exe"
$action = New-ScheduledTaskAction -Execute $binary -Argument "tray"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Haitoo HubStudio local agent" -Force
