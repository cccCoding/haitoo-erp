"""更新失败记录与受控人工重试；不修改系统安全设置。"""
import errno
from pathlib import Path

RETRYABLE = {'LAUNCH_PERMISSION_DENIED', 'NEW_VERSION_START_FAILED', 'UPDATE_LAUNCH_FAILED', 'UPDATE_INTERRUPTED'}


def launch_error(exc):
    if isinstance(exc, PermissionError) or getattr(exc, 'errno', None) in {errno.EACCES, errno.EPERM} or getattr(exc, 'winerror', None) in {5, 577, 1260}:
        return 'LAUNCH_PERMISSION_DENIED'
    return 'UPDATE_LAUNCH_FAILED'


def record_failure(root, manifest, code, release_id=None):
    from updater import atomic
    root = Path(root)
    value = {'status': 'manual_required', 'manual_required': True, 'error_code': code,
             'target_version': manifest.get('version', ''), 'failed_sha256': manifest.get('sha256', ''),
             'distribution': manifest.get('distribution', 'signed')}
    if release_id is not None:value['release_id'] = str(release_id)
    # 身份、令牌、服务器响应原文及堆栈均不进入设备心跳。
    atomic(root / 'update-result.json', value)
    atomic(root / 'failed-agent.json', {'id': release_id, 'manifest': manifest, 'error_code': code})
    return value


def retry_failed(root):
    from updater import read, atomic, keys, target
    from package_security import verify_manifest
    root = Path(root)
    failed = read(root / 'failed-agent.json', {})
    if (root / 'pending-agent.json').exists() or failed.get('error_code') not in RETRYABLE:
        return False
    manifest = verify_manifest(failed['manifest'], keys(), *target())
    blocked = read(root / 'blocked-releases.json', [])
    atomic(root / 'blocked-releases.json', [item for item in blocked if item != manifest['sha256']])
    atomic(root / 'update-result.json', {'status': 'retry_requested', 'manual_required': False})
    # 重新通过服务器选版、下载和校验，不直接运行失败目录，也不允许绕过包签名。
    return True


def confirm_manual_install(root):
    """本机启动健康检查通过后，确认手动安装的同版或更新版，清除旧失败提示。"""
    from updater import read, atomic, keys, target, VERSION
    from package_security import verify_manifest, version_tuple
    root=Path(root)
    result=read(root/'update-result.json',{})
    if not result.get('manual_required') or (root/'pending-agent.json').exists():return False
    try:
        failed=read(root/'failed-agent.json',{})
        manifest=verify_manifest(failed['manifest'],keys(),*target())
        if version_tuple(VERSION)<version_tuple(manifest['version']):return False
    except (ValueError,OSError,KeyError,TypeError):return False
    atomic(root/'update-result.json',{'status':'manual_installed','manual_required':False,'version':VERSION})
    return True
