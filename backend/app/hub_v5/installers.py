"""首次下载与自动更新共用平台稳定发布记录，不再扫描服务器本地目录。"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from typing import Literal
from ..models import HubAgent, Role
from .permissions import company_view
from ..database import get_db
from .api import matrix_user
from .connector_releases import TARGETS, applicable, download, installer_download_link
from . import service as s

router = APIRouter(prefix='/hub-v5', tags=['Agent安装包'])


def visible_agent(db, actor, identity):
    if identity is None:return None
    agent=db.get(HubAgent,identity)
    if not agent or agent.company_id!=actor.company_id or not (agent.user_id==actor.id or actor.role==Role.COMPANY_ADMIN or company_view(db,actor)):
        s.fail('设备不存在',404)
    return agent.id


def installers_impl(actor, db, distribution, agent_id):
    identity=visible_agent(db,actor,agent_id)
    items = []
    for platform, arch in sorted(TARGETS):
        for channel in (('signed','internal') if distribution=='all' else (distribution,)):
            rows = applicable(db, platform, arch, identity, channel)
            if rows:
                row = rows[0]
                items.append({'id': row.id, 'platform': platform, 'arch': arch, 'version': row.version,
                              'distribution':channel, **row.manifest['installer']})
    return {'items': items}


@router.get('/agent-installers')
def installers(distribution:Literal['signed','internal','all']='signed', agent_id:int|None=None,
               actor=Depends(matrix_user),db=Depends(get_db)):
    return installers_impl(actor,db,distribution,agent_id)


def installer_release(platform, arch, release_id, distribution, agent_id, actor, db):
    rows = applicable(db, platform, arch, visible_agent(db,actor,agent_id), distribution)
    row = next((r for r in rows if release_id is None or r.id == release_id), None)
    if not row:
        s.fail('该系统安装包尚未提供或已撤回，请刷新下载列表', 404)
    return row


@router.get('/agent-installers/{platform}/{arch}/file')
def installer_download(platform: str, arch: str, release_id: int | None = None,
                       distribution:Literal["signed","internal"]="signed", agent_id:int|None=None, actor=Depends(matrix_user), db=Depends(get_db)):
    return download(installer_release(platform, arch, release_id, distribution, agent_id, actor, db), 'installer')


@router.post('/agent-installers/{platform}/{arch}/download-url')
def installer_download_url(platform: str, arch: str, release_id: int | None = None,
                           distribution:Literal["signed","internal"]="signed", agent_id:int|None=None, actor=Depends(matrix_user), db=Depends(get_db)):
    row = installer_release(platform, arch, release_id, distribution, agent_id, actor, db)
    return JSONResponse(installer_download_link(row), headers={'Cache-Control': 'private, no-store'})
