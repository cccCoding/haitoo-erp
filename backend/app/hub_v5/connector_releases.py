"""平台连接器发布：不可变签名文件、测试设备、稳定下载及撤回。"""
import asyncio
import hashlib
import json
from uuid import uuid4
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..database import get_db
from ..models import HubAgent, Role
from ..security import require_roles
from ..storage import _export_configuration, _r2_client
from .api import agent_auth
from .models import ConnectorRelease
from .releases import MAX_PACKAGE, validate_manifest
from . import service as s

router = APIRouter(tags=['平台连接器发布'])
platform_admin = require_roles(Role.SUPER_ADMIN)
TARGETS = {('windows', 'x64'), ('macos', 'arm64'), ('macos', 'x64')}


def location(manifest, kind):
    endpoint, access, secret, bucket = _export_configuration()
    checksum = manifest['sha256'] if kind == 'update' else manifest['installer']['sha256']
    # 内容寻址：重传相同文件是幂等的，不会改变正在下载的文件。
    key = f'connector/{manifest["version"]}/{manifest["platform"]}-{manifest["arch"]}/{checksum}/{kind}'
    return _r2_client(endpoint, access, secret), bucket, key


def summary(row):
    return {k: getattr(row, k) for k in ('id', 'version', 'platform', 'arch', 'manifest', 'stage', 'test_agent_ids', 'revision', 'history')}


def applicable(db, platform, arch, agent_id=None, distribution="signed"):
    if (platform, arch) not in TARGETS:
        return []
    rows = db.scalars(select(ConnectorRelease).where(
        ConnectorRelease.platform == platform, ConnectorRelease.arch == arch,
        ConnectorRelease.stage.in_(['stable', 'test']))).all()
    return sorted((r for r in rows if r.manifest.get('distribution','signed') == distribution and (r.stage == 'stable' or agent_id in r.test_agent_ids)),
                  key=lambda r: tuple(map(int, r.version.split('.'))), reverse=True)


def download(row, kind):
    info = row.manifest if kind == 'update' else row.manifest['installer']
    try:
        client, bucket, key = location(row.manifest, kind)
        result = client.get_object(Bucket=bucket, Key=key)
    except Exception:
        s.fail('发布文件暂不可用，请稍后重试', 503)
    body = result['Body']
    if result.get('ContentLength') != info['size']:
        body.close()
        s.fail('发布文件大小不一致', 502)
    def chunks():
        try:
            while chunk := body.read(1024 * 1024):
                yield chunk
        finally:
            body.close()
    filename = f'HaitooHubAgent-{row.platform}-{row.arch}-{row.version}-update.zip' if kind == 'update' else info['filename']
    return StreamingResponse(chunks(), media_type='application/octet-stream', headers={
        'Content-Length': str(info['size']), 'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff', 'X-Checksum-SHA256': info['sha256'],
        'Content-Disposition': f"attachment; filename*=UTF-8''{quote(filename)}"})


def installer_download_link(row):
    """权限校验后签发短时私有链接；安装包由浏览器直接流式下载。"""
    info = row.manifest['installer']
    expires_in = 300
    try:
        client, bucket, key = location(row.manifest, 'installer')
        metadata = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        s.fail('发布文件暂不可用，请稍后重试', 503)
    if metadata.get('ContentLength') != info['size']:
        s.fail('发布文件大小不一致', 502)
    try:
        url = client.generate_presigned_url('get_object', Params={
            'Bucket': bucket, 'Key': key,
            'ResponseContentDisposition': f"attachment; filename*=UTF-8''{quote(info['filename'], safe='')}",
            'ResponseContentType': 'application/octet-stream',
            'ResponseCacheControl': 'private, no-store',
        }, ExpiresIn=expires_in)
    except Exception:
        s.fail('下载链接暂不可用，请稍后重试', 503)
    return {'url': url, 'expires_in': expires_in, 'filename': info['filename']}


@router.get('/admin/connector-releases')
def list_releases(actor=Depends(platform_admin), db=Depends(get_db)):
    rows = []
    for row in db.scalars(select(ConnectorRelease).order_by(ConnectorRelease.id.desc()).limit(200)):
        item = summary(row)
        item['manifest'] = {key:value for key,value in row.manifest.items() if key not in {'files','symlinks'}}
        rows.append(item)
    return rows


@router.post('/admin/connector-releases')
async def publish(manifest_json: str = Form(...), artifact: UploadFile = File(...),
                  installer: UploadFile = File(...), actor=Depends(platform_admin), db=Depends(get_db)):
    if len(manifest_json) > 3 * 1024 * 1024:
        s.fail('清单过大', 413)
    try:
        manifest = json.loads(manifest_json)
    except ValueError:
        s.fail('清单 JSON 无效', 422)
    validate_manifest(manifest)
    if manifest['kind'] != 'agent' or (manifest['platform'], manifest['arch']) not in TARGETS:
        s.fail('仅支持 Windows x64、macOS Apple 芯片及 Intel 连接器', 422)
    if not {'installer', 'min_launcher_version'}.issubset(manifest):
        s.fail('须使用同时签署安装包和更新包的正式清单', 422)
    prior = db.scalar(select(ConnectorRelease).where(ConnectorRelease.version == manifest['version'],
        ConnectorRelease.platform == manifest['platform'], ConnectorRelease.arch == manifest['arch']))
    if prior:
        if prior.manifest != manifest:
            s.fail('同版本内容不可更改，请增加版本号', 409)
        return summary(prior)
    for kind, upload, info in [('update', artifact, manifest), ('installer', installer, manifest['installer'])]:
        if upload.size is not None and upload.size > MAX_PACKAGE:
            s.fail('发布文件超过 250MB', 413)
        # UploadFile 在磁盘暂存；上传与读回均分块，不同时持有两个大文件。
        checksum = hashlib.sha256(); size = 0
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > info['size']:
                s.fail('发布文件大小不一致', 422)
            checksum.update(chunk)
        if size != info['size'] or checksum.hexdigest() != info['sha256']:
            s.fail('发布文件摘要不一致', 422)
        await upload.seek(0)
        def store():
            client, bucket, key = location(manifest, kind)
            client.put_object(Bucket=bucket, Key=key, Body=upload.file,
                              ContentType='application/octet-stream', CacheControl='private, no-store')
            body = client.get_object(Bucket=bucket, Key=key)['Body']
            digest = hashlib.sha256(); received = 0
            try:
                while chunk := body.read(1024 * 1024):
                    received += len(chunk); digest.update(chunk)
                    if received > info['size']:
                        raise ValueError('存储文件过大')
            finally:
                body.close()
            if received != info['size'] or digest.hexdigest() != info['sha256']:
                raise ValueError('存储文件校验失败')
        try:
            await asyncio.to_thread(store)
        except Exception:
            s.fail('发布包私有存储失败或读回校验失败', 503)
    row = ConnectorRelease(version=manifest['version'], platform=manifest['platform'], arch=manifest['arch'],
        manifest=manifest, stage='draft', test_agent_ids=[], revision=1,
        history=[{'actor_id': actor.id, 'action': 'upload', 'at': datetime.utcnow().isoformat()}])
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback(); s.fail('该版本已由其他管理员上传，请刷新', 409)
    return summary(row)


@router.post('/admin/connector-releases/uploads')
def prepare_upload(manifest: dict, actor=Depends(platform_admin), db=Depends(get_db)):
    if len(json.dumps(manifest)) > 3 * 1024 * 1024:s.fail('清单过大', 413)
    validate_manifest(manifest)
    if manifest['kind'] != 'agent' or (manifest['platform'],manifest['arch']) not in TARGETS or not {'installer','min_launcher_version'}.issubset(manifest):
        s.fail('须提供受支持系统的正式连接器清单',422)
    row=db.scalar(select(ConnectorRelease).where(ConnectorRelease.version==manifest['version'],
        ConnectorRelease.platform==manifest['platform'],ConnectorRelease.arch==manifest['arch']).with_for_update())
    if row and row.manifest!=manifest:s.fail('同版本内容不可更改，请增加版本号',409)
    if not row:
        row=ConnectorRelease(version=manifest['version'],platform=manifest['platform'],arch=manifest['arch'],manifest=manifest,
            stage='uploading',upload_nonce=str(uuid4()),revision=1,test_agent_ids=[],
            history=[{'actor_id':actor.id,'action':'prepare_upload','at':datetime.utcnow().isoformat()}])
        db.add(row)
        try:db.commit()
        except IntegrityError:
            db.rollback();s.fail('版本已由其他管理员创建，请刷新',409)
    if row.stage!='uploading':return summary(row)
    urls={}
    try:
        for kind in ('update','installer'):
            client,bucket,_=location(manifest,kind)
            urls[kind]=client.generate_presigned_url('put_object',Params={'Bucket':bucket,
                'Key':f'connector-staging/{row.upload_nonce}/{kind}','ContentType':'application/octet-stream'},ExpiresIn=900)
    except Exception:s.fail('私有存储暂不可用，请检查 R2 配置',503)
    return {**summary(row),'uploads':urls}


@router.post('/admin/connector-releases/{identity}/complete')
async def complete_upload(identity:int,actor=Depends(platform_admin),db=Depends(get_db)):
    row=db.scalar(select(ConnectorRelease).where(ConnectorRelease.id==identity).with_for_update())
    if not row:s.fail('发布记录不存在',404)
    if row.stage!='uploading':return summary(row)
    validate_manifest(row.manifest)
    def finalize():
        for kind in ('update','installer'):
            info=row.manifest if kind=='update' else row.manifest['installer']
            client,bucket,key=location(row.manifest,kind)
            source=f'connector-staging/{row.upload_nonce}/{kind}'
            result=client.get_object(Bucket=bucket,Key=source)
            body=result['Body'];digest=hashlib.sha256();size=0
            try:
                while chunk:=body.read(1024*1024):
                    size+=len(chunk)
                    if size>info['size']:raise ValueError('发布文件过大')
                    digest.update(chunk)
            finally:body.close()
            if size!=info['size'] or digest.hexdigest()!=info['sha256']:raise ValueError('发布文件摘要不一致')
            # 固定 ETag 复制已验证的对象；临时 URL 不能修改最终发布目录。
            client.copy_object(Bucket=bucket,Key=key,CopySource={'Bucket':bucket,'Key':source},
                               CopySourceIfMatch=result['ETag'],MetadataDirective='REPLACE',
                               ContentType='application/octet-stream',CacheControl='private, no-store')
    try:await asyncio.to_thread(finalize)
    except ValueError:s.fail('发布文件校验失败，请选择正确文件并重新上传',422)
    except Exception:s.fail('上传未完成或存储校验失败，请重新上传后重试',503)
    row.stage='draft';row.revision+=1
    row.history=[*row.history,{'actor_id':actor.id,'action':'upload_verified','at':datetime.utcnow().isoformat()}]
    db.commit()
    for kind in ('update','installer'):
        try:
            client,bucket,_=location(row.manifest,kind)
            client.delete_object(Bucket=bucket,Key=f'connector-staging/{row.upload_nonce}/{kind}')
        except Exception:pass  # 临时前缀另配一天生命周期，清理失败不影响已验证的发布。
    return summary(row)


class StageInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: str
    revision: StrictInt
    test_agent_ids: list[StrictInt] = Field(default_factory=list, max_length=200)


@router.put('/admin/connector-releases/{identity}/stage')
def set_stage(identity: int, payload: StageInput, actor=Depends(platform_admin), db=Depends(get_db)):
    row = db.scalar(select(ConnectorRelease).where(ConnectorRelease.id == identity).with_for_update())
    if not row:
        s.fail('发布记录不存在', 404)
    if row.revision != payload.revision:
        s.fail('发布状态已变化，请刷新后重试', 409)
    allowed = {'draft': {'test', 'stable', 'withdrawn'}, 'test': {'test', 'stable', 'withdrawn'},
               'stable': {'withdrawn'}, 'withdrawn': set()}
    if payload.stage not in allowed.get(row.stage, set()):
        s.fail('不允许的发布状态变更；已撤回的版本不能重新开放', 422)
    ids = sorted(set(payload.test_agent_ids)) if payload.stage == 'test' else []
    if payload.stage == 'test':
        if not ids or len(db.scalars(select(HubAgent.id).where(HubAgent.id.in_(ids), HubAgent.is_active.is_(True))).all()) != len(ids):
            s.fail('请选择有效的测试设备 ID', 422)
    row.stage, row.test_agent_ids = payload.stage, ids
    row.revision += 1
    row.history = [*row.history, {'actor_id': actor.id, 'action': payload.stage, 'test_agent_ids': ids,
                                'at': datetime.utcnow().isoformat()}]
    db.commit()
    return summary(row)


@router.get('/hub-v5/agent/connector-releases')
def agent_releases(platform: str, arch: str, distribution: str = "signed", agent=Depends(agent_auth), db=Depends(get_db)):
    # 只下发最高适用版本；故障版本隔离后等待修复版，避免在多个坏版本间循环。
    return [{'id': r.id, 'manifest': r.manifest} for r in applicable(db, platform, arch, agent.id, distribution)[:1]]


@router.get('/hub-v5/agent/connector-releases/{identity}/file')
def agent_file(identity: int, agent=Depends(agent_auth), db=Depends(get_db)):
    row = db.get(ConnectorRelease, identity)
    if not row or row.stage not in {'stable', 'test'} or row.stage == 'test' and agent.id not in row.test_agent_ids:
        s.fail('发布包已撤回或未向该设备开放', 404)
    validate_manifest(row.manifest)
    return download(row, 'update')
