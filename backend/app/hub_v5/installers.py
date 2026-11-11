"""首次下载与自动更新共用平台稳定发布记录，不再扫描服务器本地目录。"""
from fastapi import APIRouter, Depends
from ..database import get_db
from .api import matrix_user
from .connector_releases import TARGETS, applicable, download
from . import service as s

router = APIRouter(prefix='/hub-v5', tags=['Agent安装包'])


@router.get('/agent-installers')
def installers(actor=Depends(matrix_user), db=Depends(get_db)):
    items = []
    for platform, arch in sorted(TARGETS):
        rows = applicable(db, platform, arch)
        if rows:
            row = rows[0]
            items.append({'id': row.id, 'platform': platform, 'arch': arch, 'version': row.version,
                          **row.manifest['installer']})
    return {'items': items}


@router.get('/agent-installers/{platform}/{arch}/file')
def installer_download(platform: str, arch: str, release_id: int | None = None,
                       actor=Depends(matrix_user), db=Depends(get_db)):
    rows = applicable(db, platform, arch)
    row = next((r for r in rows if release_id is None or r.id == release_id), None)
    if not row:
        s.fail('该系统安装包尚未提供或已撤回，请刷新下载列表', 404)
    return download(row, 'installer')
