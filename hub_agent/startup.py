"""当前桌面用户登录自启；不创建系统服务，也不要求管理员权限。"""
import json
import os
import platform
import plistlib
import subprocess
from pathlib import Path


def configure(enabled, command):
    if platform.system() == 'Windows':
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            if enabled:
                winreg.SetValueEx(key, 'HaitooHubAgent', 0, winreg.REG_SZ, subprocess.list2cmdline(command))
            else:
                try: winreg.DeleteValue(key, 'HaitooHubAgent')
                except FileNotFoundError: pass
    elif platform.system() == 'Darwin':
        path = Path.home() / 'Library/LaunchAgents/com.haitoo.hub-agent.plist'
        if enabled:
            if str(command[0]).startswith('/Volumes/'):
                raise RuntimeError('请先把连接器拖入应用程序目录，再开启登录自启')
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {'Label': 'com.haitoo.hub-agent', 'ProgramArguments': command, 'RunAtLoad': True, 'ProcessType': 'Interactive'}
            temporary = path.with_suffix('.tmp')
            temporary.write_bytes(plistlib.dumps(data)); temporary.replace(path)
        else:
            path.unlink(missing_ok=True)
    else:
        raise RuntimeError('此系统不支持连接器登录自启')


def bootstrap_command():
    from updater import current_command
    return json.loads(os.environ.get('HAITOO_BOOTSTRAP_COMMAND', json.dumps(current_command())))


def migrate_legacy():
    """仅清理旧连接器的当前用户同名计划任务，保留其他用户及应用任务。"""
    if platform.system() == 'Windows':
        script = """$t = Get-ScheduledTask -TaskName HaitooHubAgent -ErrorAction SilentlyContinue;
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value;
if ($t -and $t.Principal.UserId -in @($env:USERNAME, "$env:USERDOMAIN\\$env:USERNAME", $sid)) {
Unregister-ScheduledTask -TaskName HaitooHubAgent -Confirm:$false -ErrorAction Stop
}"""
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], check=True, capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
