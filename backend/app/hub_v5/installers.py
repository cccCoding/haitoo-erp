"""首次安装包下载；目录由部署配置，用户不能指定本机路径。"""
import re
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from ..config import get_settings
from .api import matrix_user

router = APIRouter(prefix='/hub-v5', tags=['Agent安装包'])
NAME = re.compile(r'^HaitooHubAgent-(windows|macos)-(x64|arm64)-(\d+\.\d+\.\d+)\.zip$')


def installer_files():
    root = Path(get_settings().hub_agent_installer_dir).resolve()
    latest = {}
    if not root.is_dir():
        return latest
    for path in root.iterdir():
        match = NAME.fullmatch(path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        platform, arch, version = match.groups()
        key = (platform, arch)
        row = {'platform':platform, 'arch':arch, 'version':version, 'filename':path.name, 'size':path.stat().st_size}
        if row['size'] <= 0 or row['size'] > 250 * 1024 * 1024:
            continue
        if key not in latest or tuple(map(int,version.split('.'))) > tuple(map(int,latest[key]['version'].split('.'))):
            latest[key] = row
    return latest


@router.get('/agent-installers')
def installers(actor=Depends(matrix_user)):
    return {'items':list(installer_files().values())}


@router.get('/agent-installers/{platform}/{arch}/file')
def installer_download(platform:str, arch:str, actor=Depends(matrix_user)):
    row = installer_files().get((platform,arch))
    if not row:
        raise HTTPException(404, '该系统的Agent安装包尚未提供，请联系管理员')
    path = Path(get_settings().hub_agent_installer_dir).resolve() / row['filename']
    return FileResponse(path,media_type='application/zip',filename=row['filename'],headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
