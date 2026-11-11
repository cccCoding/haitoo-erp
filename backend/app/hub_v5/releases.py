"""公司隔离的签名发布仓；服务端只持有发布公钥。"""
import base64
import hashlib
import json
import re
import asyncio
from fastapi import APIRouter, Depends, UploadFile, File, Form, Response
from sqlalchemy import select
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from ..config import get_settings
from ..database import get_db
from ..security import current_internal_user
from ..storage import _export_configuration, _r2_client, StorageError
from .models import MatrixRelease
from .api import admin, agent_auth, matrix_user
from . import service as s

router=APIRouter(prefix="/hub-v5",tags=["矩阵签名发布"])
MAX_PACKAGE=250*1024*1024


def validate_manifest(manifest):
    required={"kind","version","platform","arch","sha256","size","key_id","signature","protocol_min","protocol_max","entrypoint","files"}
    if not isinstance(manifest,dict) or not required.issubset(manifest) or set(manifest)-required-{"installer", "min_launcher_version", "symlinks"}:s.fail("发布清单字段不正确",422)
    if any(not isinstance(manifest[k],str) for k in ("kind","version","platform","arch","sha256","key_id","signature","entrypoint")):s.fail("发布清单类型不正确",422)
    if manifest["kind"] not in {"agent","plugin"} or manifest["platform"] not in {"windows","macos"} or manifest["arch"] not in {"x64","arm64"}:s.fail("发布目标不受支持",422)
    if not re.fullmatch(r"\d+\.\d+\.\d+",manifest["version"]):s.fail("版本必须是三段数字",422)
    if type(manifest["size"]) is not int or not 0<manifest["size"]<=MAX_PACKAGE or not re.fullmatch(r"[a-f0-9]{64}",manifest["sha256"]):s.fail("发布文件摘要无效",422)
    if not isinstance(manifest["files"],dict) or not 1<=len(manifest["files"])<=20000:s.fail("发布文件清单无效",422)
    if type(manifest["protocol_min"]) is not int or type(manifest["protocol_max"]) is not int or not manifest["protocol_min"]<=5<=manifest["protocol_max"]:s.fail("发布协议范围不兼容",422)
    for path,checksum in manifest["files"].items():
        if not isinstance(path,str) or path.startswith("/") or "\\" in path or ":" in path or any(p in {"", ".", ".."} for p in path.split("/")) or not isinstance(checksum,str) or not re.fullmatch(r"[a-f0-9]{64}",checksum):s.fail("发布文件路径不安全",422)
    if "installer" in manifest:
        item=manifest["installer"]
        extension="exe" if manifest["platform"]=="windows" else "dmg"
        expected=f'HaitooHubAgent-{manifest["platform"]}-{manifest["arch"]}-{manifest["version"]}.{extension}'
        if not isinstance(item,dict) or set(item)!={"filename","size","sha256"} or item["filename"]!=expected or type(item["size"]) is not int or not 0<item["size"]<=MAX_PACKAGE or not isinstance(item["sha256"],str) or not re.fullmatch(r"[a-f0-9]{64}",item["sha256"]):s.fail("首次安装包清单无效",422)
    if "min_launcher_version" in manifest and (not isinstance(manifest["min_launcher_version"],str) or not re.fullmatch(r"\d+\.\d+\.\d+",manifest["min_launcher_version"])):s.fail("启动入口版本无效",422)
    links=manifest.get("symlinks",{})
    if not isinstance(links,dict) or manifest["platform"]!="macos" and links:s.fail("链接清单无效",422)
    from pathlib import PurePosixPath
    for name,target in links.items():
        if name not in manifest["files"] or not isinstance(target,str) or not target or target.startswith("/") or "\\" in target or ":" in target:s.fail("链接路径无效",422)
        parts=list(PurePosixPath(name).parent.parts)
        for part in target.split("/"):
            if part=="..":
                if not parts:s.fail("链接越出发布目录",422)
                parts.pop()
            elif part not in {"", "."}:parts.append(part)
    if manifest["entrypoint"] not in manifest["files"]:s.fail("启动入口不在签名文件清单中",422)
    try:
        keys=json.loads(get_settings().matrix_release_public_keys)
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(keys[manifest["key_id"]],validate=True))
        key.verify(base64.b64decode(manifest["signature"],validate=True),json.dumps({k:v for k,v in manifest.items() if k!="signature"},ensure_ascii=False,sort_keys=True,separators=(",",":")).encode())
    except Exception:s.fail("发布签名无效或公钥未配置",422)
    return manifest


def location(company,checksum):
    endpoint,access,secret,bucket=_export_configuration()
    return _r2_client(endpoint,access,secret),bucket,f"matrix-releases/company/{company}/{checksum}.zip"


@router.post("/releases")
async def publish(manifest_json:str=Form(...),enabled:bool=Form(False),artifact:UploadFile=File(...),actor=Depends(matrix_user),db=Depends(get_db)):
    admin(actor)
    if len(manifest_json)>3*1024*1024:s.fail("清单过大",413)
    try:manifest=json.loads(manifest_json)
    except ValueError:s.fail("清单JSON无效",422)
    validate_manifest(manifest)
    if manifest["kind"]!="plugin":s.fail("连接器由平台管理员统一发布，请使用平台发布入口",403)
    if artifact.size is not None and artifact.size>MAX_PACKAGE:s.fail("发布包过大",413)
    content=await artifact.read(manifest["size"]+1)
    if len(content)!=manifest["size"] or hashlib.sha256(content).hexdigest()!=manifest["sha256"]:s.fail("发布包校验失败",422)
    try:client,bucket,key=location(actor.company_id,manifest["sha256"])
    except StorageError:s.fail("发布包私有存储尚未配置",503)
    def store():
        client.put_object(Bucket=bucket,Key=key,Body=content,ContentType="application/zip",CacheControl="private, no-store")
        body=client.get_object(Bucket=bucket,Key=key)["Body"]
        try:stored=body.read(len(content)+1)
        finally:body.close()
        if hashlib.sha256(stored).hexdigest()!=manifest["sha256"]:raise StorageError("发布包摘要错误")
    try:
        await asyncio.to_thread(store)
    except StorageError:s.fail("发布包存储校验失败",502)
    except Exception:s.fail("发布包存储失败",503)
    s.guard(db,actor.company_id)
    admin(actor)
    prior=db.scalar(select(MatrixRelease).where(MatrixRelease.company_id==actor.company_id,MatrixRelease.kind==manifest["kind"],MatrixRelease.version==manifest["version"],MatrixRelease.platform==manifest["platform"],MatrixRelease.arch==manifest["arch"]))
    if prior:
        if prior.manifest!=manifest:s.fail("同版本发布内容不可更改")
        prior.enabled=enabled;row=prior
    else:
        row=MatrixRelease(company_id=actor.company_id,kind=manifest["kind"],version=manifest["version"],platform=manifest["platform"],arch=manifest["arch"],manifest=manifest,enabled=enabled)
        db.add(row);db.flush()
    s.audit(db,actor,"release.publish",row.id,{"sha256":manifest["sha256"],"enabled":enabled});db.commit()
    return {"id":row.id,"enabled":row.enabled,"manifest":row.manifest}


@router.get("/releases")
def releases(actor=Depends(matrix_user),db=Depends(get_db)):
    admin(actor)
    return [{"id":r.id,"enabled":r.enabled,"manifest":r.manifest} for r in db.scalars(select(MatrixRelease).where(MatrixRelease.company_id==actor.company_id,MatrixRelease.kind=="plugin").order_by(MatrixRelease.id.desc()).limit(100))]


@router.post("/releases/{identity}/disable")
def disable(identity:int,actor=Depends(matrix_user),db=Depends(get_db)):
    admin(actor);s.guard(db,actor.company_id);admin(actor)
    row=s.owned(db,MatrixRelease,identity,actor);row.enabled=False
    s.audit(db,actor,"release.disable",identity,{});db.commit();return {"enabled":False}


@router.get("/agent/releases")
def agent_releases(platform:str,arch:str,agent=Depends(agent_auth),db=Depends(get_db)):
    rows=db.scalars(select(MatrixRelease).where(MatrixRelease.company_id==agent.company_id,MatrixRelease.kind=="plugin",MatrixRelease.enabled.is_(True),MatrixRelease.platform==platform,MatrixRelease.arch==arch).order_by(MatrixRelease.id.desc()).limit(100)).all()
    return [{"id":r.id,"manifest":r.manifest} for r in rows]


@router.get("/agent/releases/{identity}/file")
def release_file(identity:int,agent=Depends(agent_auth),db=Depends(get_db)):
    row=db.get(MatrixRelease,identity)
    if not row or row.company_id!=agent.company_id or not row.enabled or row.kind!="plugin":s.fail("发布包不存在",404)
    validate_manifest(row.manifest)
    client,bucket,key=location(agent.company_id,row.manifest["sha256"])
    body=client.get_object(Bucket=bucket,Key=key)["Body"]
    try:content=body.read(row.manifest["size"]+1)
    finally:body.close()
    if len(content)!=row.manifest["size"] or hashlib.sha256(content).hexdigest()!=row.manifest["sha256"]:s.fail("发布包存储校验失败",502)
    return Response(content,media_type="application/zip",headers={"Cache-Control":"no-store"})
