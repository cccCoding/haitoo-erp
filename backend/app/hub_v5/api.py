"""ERP 会话与受限设备令牌使用不同的协议5入口。"""
import csv
import io
import secrets
from urllib.parse import quote
from decimal import Decimal
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Request, Query, Response, HTTPException
from sqlalchemy import select, func, or_
from ..database import get_db
from ..security import current_user
from ..models import HubAgent, HubUploadTask, User, Role, Company
from .. import hub
from ..supply_common import digest
from .models import *
from .schemas import *
from . import service as s, collections as c, listing, permissions

router = APIRouter(prefix="/hub-v5", tags=["TK矩阵管理"])


def internal_actor(actor=Depends(current_user), db=Depends(get_db)):
    if not actor.company_id or actor.role not in permissions.ROLES: s.fail("请使用已支持矩阵的公司账号",403)
    company=db.get(Company,actor.company_id)
    if not company or not company.is_active:s.fail("公司不可用",403)
    db.info["matrix_authenticated"] = {"user_id": actor.id, "token_version": actor.token_version}
    return actor


def matrix_user(actor=Depends(internal_actor), db=Depends(get_db)):
    permissions.require_access(db, actor)
    return actor


def matrix_admin(actor=Depends(internal_actor)):
    admin(actor)
    return actor


@router.get("/access")
def my_access(actor=Depends(internal_actor), db=Depends(get_db)):
    return permissions.access(db, actor)


def agent_auth(request: Request, db=Depends(get_db)):
    if request.headers.get("X-Hub-Protocol") != "5": s.fail("需要协议5", 426)
    from ..main import hub_agent_from_request
    agent = hub_agent_from_request(request, db)
    owner = db.get(User, agent.user_id)
    if owner.role not in permissions.ROLES: s.fail("账号不能运行矩阵任务", 403)
    db.info["matrix_authenticated"] = {"user_id": owner.id, "agent_id": agent.id, "token_hash": agent.token_hash}
    return agent


def admin(actor):
    if actor.role != Role.COMPANY_ADMIN: s.fail("仅公司管理员可操作", 403)


@router.get("/config")
def config(actor=Depends(matrix_user), db=Depends(get_db)):
    row = db.get(MatrixCompany, actor.company_id)
    return {"enabled": bool(row and row.enabled), "listing_enabled": bool(row and row.enabled)}


@router.put("/config")
def set_config(payload: CompanyInput, actor=Depends(matrix_user), db=Depends(get_db)):
    s.fail("请在 admin 公司配置中设置启用 TK 矩阵", 403)


@router.get("/agents")
def agents(actor=Depends(matrix_user), db=Depends(get_db)):
    query = select(HubAgent).where(HubAgent.company_id == actor.company_id)
    query = query.where(HubAgent.user_id == actor.id)
    return [s.device_view(db, a) for a in db.scalars(query.order_by(HubAgent.name))]


@router.get("/agent/config")
def agent_config(agent=Depends(agent_auth), db=Depends(get_db)):
    owner = db.get(User, agent.user_id)
    return {"user": {"id": owner.id, "name": owner.name}, "configured": True,
        "protocol": 5, **config(owner, db), "permissions": permissions.access(db, owner)}


@router.post("/agent/heartbeat")
def heartbeat(payload: Heartbeat, agent=Depends(agent_auth), db=Depends(get_db)):
    s.guard(db, agent.company_id)
    device = db.get(MatrixDevice, agent.id)
    occupied = db.scalar(select(MatrixDevice).where(MatrixDevice.install_uuid == str(payload.install_uuid)))
    if occupied and occupied.agent_id != agent.id:
        previous = db.get(HubAgent, occupied.agent_id)
        if not previous or previous.is_active or previous.company_id != agent.company_id or previous.user_id != agent.user_id:
            s.fail("安装身份已被另一设备授权使用，请核对原设备授权")
        if db.scalar(select(MatrixRun.id).where(MatrixRun.agent_id == previous.id, MatrixRun.status.in_(["queued", "running", "awaiting_attention"]))):
            s.fail("请先在 ERP 处理原连接器未结束的运行")
        if db.scalar(select(HubUploadTask.id).where(HubUploadTask.agent_id == previous.id, HubUploadTask.status.in_(["running", "awaiting_attention"]))):
            s.fail("请先在 ERP 处理原连接器的旧版上品任务")
        for access in db.scalars(select(MatrixAccess).where(MatrixAccess.agent_id == previous.id)): access.available = False
        db.delete(occupied)
        db.flush()
    if device and device.install_uuid != str(payload.install_uuid): s.fail("设备安装身份不一致，请重新配对")
    if not device:
        device = MatrixDevice(agent_id=agent.id, install_uuid=str(payload.install_uuid), version=payload.version, hub_identity=payload.hub_identity or "")
        db.add(device)
    # 新连接器省略身份，始终使用 ERP 保存的配置；保留旧协议5的显式身份兼容。
    if payload.hub_identity is not None and device.hub_identity != payload.hub_identity:
        device.sync_at = None
        for access in db.scalars(select(MatrixAccess).where(MatrixAccess.agent_id == agent.id)): access.available = False
        device.hub_identity = payload.hub_identity
    device.version, device.hub_connected = payload.version, payload.hub_connected
    device.capabilities = payload.capabilities
    device.local_paused = payload.local_paused
    # 状态仅取公开枚举，不接收路径、异常原文或凭据。
    device.update_state = {k: str(v)[:100] for k,v in payload.update_state.items() if k in {"status", "version", "plugin_version", "plugin_digest", "error_code", "target_version", "progress", "distribution", "failed_sha256", "release_id"}}
    device.update_state["manual_required"] = payload.update_state.get("manual_required") is True
    db.commit()
    owner = db.get(User, agent.user_id)
    grant = permissions.access(db, owner)
    conf = config(owner, db)
    return {"paused": device.paused, "hub_identity": device.hub_identity, "permissions": grant,
        "enabled": conf["enabled"] and grant["enabled"], "listing_enabled": conf["listing_enabled"] and grant["listing_enabled"]}


@router.put("/agents/{identity}/connection")
def set_connection(identity: int, payload: ConnectionInput, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db, actor.company_id)
    agent = db.get(HubAgent, identity)
    if not agent or not agent.is_active or agent.company_id != actor.company_id or not getattr(actor, "platform_management", False) and agent.user_id != actor.id:
        s.fail("设备不存在", 404)
    device = db.get(MatrixDevice, identity)
    if not device: s.fail("请先启动新版连接器")
    if device.hub_identity != payload.hub_identity:
        if db.scalar(select(MatrixRun.id).where(MatrixRun.agent_id == identity, MatrixRun.status.in_(["queued", "running", "awaiting_attention"]))):
            s.fail("请先结束或处理此设备的运行，再修改 Hub 团队身份")
        if db.scalar(select(HubUploadTask.id).where(HubUploadTask.agent_id == identity, HubUploadTask.status.in_(["running", "awaiting_attention"]))):
            s.fail("请先处理此设备的旧版上品任务")
        before = device.hub_identity
        device.hub_identity, device.sync_at = payload.hub_identity, None
        for access in db.scalars(select(MatrixAccess).where(MatrixAccess.agent_id == identity)): access.available = False
        s.audit(db, actor, "device.connection", identity, {"before": before, "after": payload.hub_identity})
    db.commit()
    return s.device_view(db, agent)


@router.post("/agents/{identity}/commands")
def device_command(identity: int, payload: DeviceCommand, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db, actor.company_id)
    agent = db.get(HubAgent, identity)
    if not agent or agent.company_id != actor.company_id or not getattr(actor, "platform_management", False) and agent.user_id != actor.id: s.fail("设备不存在", 404)
    device = db.get(MatrixDevice, identity)
    if payload.kind == "revoke":
        admin(actor); agent.is_active = False
    elif payload.kind in {"pause", "resume"}:
        if not device: s.fail("设备尚未升级协议5")
        device.paused = payload.kind == "pause"
    if payload.kind == "refresh" and not s.device_view(db, agent)["online"]: s.fail("设备离线，无法刷新")
    command_payload={}
    if payload.kind=='retry_update':
        if not device or not agent.is_active or not s.device_view(db,agent)['online']:s.fail('设备离线或已撤销，无法请求重试')
        if not device.update_state.get('manual_required') or device.update_state.get('error_code') not in {'LAUNCH_PERMISSION_DENIED','NEW_VERSION_START_FAILED','UPDATE_LAUNCH_FAILED','UPDATE_INTERRUPTED'}:s.fail('当前失败不能直接重试，请下载新版或联系管理员')
        command_payload={'expected_sha256':device.update_state.get('failed_sha256','')}
        if len(command_payload['expected_sha256'])!=64:s.fail('缺少失败版本记录，请从本机托盘重试')
        pending=db.scalars(select(MatrixCommand).where(MatrixCommand.agent_id==identity,MatrixCommand.kind=='retry_update',MatrixCommand.acknowledged_at.is_(None),MatrixCommand.expires_at>s.utcnow())).all()
        for queued in pending:
            if queued.payload==command_payload:return {'command_id':queued.id,'status':'requested'}
    command = MatrixCommand(company_id=actor.company_id, agent_id=identity, kind=payload.kind, payload=command_payload, expires_at=s.utcnow()+(timedelta(days=1) if payload.kind=='retry_update' else timedelta(minutes=5)))
    db.add(command); s.audit(db, actor, "device."+payload.kind, identity, {}); db.commit()
    return {"command_id": command.id, "status": "requested"}


@router.get("/agent/commands")
def commands(agent=Depends(agent_auth), db=Depends(get_db)):
    return [{"id": r.id, "kind": r.kind, "payload": r.payload} for r in db.scalars(select(MatrixCommand).where(MatrixCommand.agent_id == agent.id,
        MatrixCommand.acknowledged_at.is_(None), MatrixCommand.expires_at > s.utcnow()).order_by(MatrixCommand.id).limit(100))]


@router.post("/agent/commands/{identity}/ack")
def ack(identity: int, agent=Depends(agent_auth), db=Depends(get_db)):
    s.guard(db, agent.company_id)
    row = db.get(MatrixCommand, identity)
    if not row or row.agent_id != agent.id or row.company_id != agent.company_id: s.fail("命令不存在", 404)
    if row.expires_at < s.utcnow(): s.fail("命令已过期")
    row.acknowledged_at = s.utcnow(); db.commit(); return {"acknowledged": True}


@router.post("/agent/environment-syncs")
def sync_start(payload: SyncInput, agent=Depends(agent_auth), db=Depends(get_db)):
    s.guard(db, agent.company_id); s.enabled(db, agent.company_id)
    permissions.require_access(db, db.get(User, agent.user_id))
    device = db.get(MatrixDevice, agent.id)
    if not device or device.hub_identity != payload.hub_identity: s.fail("Hub身份不一致")
    old = db.scalar(select(MatrixSync).where(MatrixSync.agent_id == agent.id, MatrixSync.snapshot_key == payload.snapshot_key))
    if old:
        if any(getattr(old,k) != v for k,v in payload.model_dump().items()): s.fail("目录快照幂等内容不一致")
        return {"id": old.id, "status": old.status}
    row = MatrixSync(company_id=agent.company_id, agent_id=agent.id, **payload.model_dump())
    db.add(row); db.commit(); return {"id": row.id, "status": row.status}


def get_sync(db, agent, identity):
    row = db.get(MatrixSync, identity)
    if not row or row.agent_id != agent.id or row.company_id != agent.company_id: s.fail("目录同步不存在", 404)
    return row


@router.put("/agent/environment-syncs/{identity}/parts/{number}")
def sync_part(identity: int, number: int, payload: DirectoryPart, agent=Depends(agent_auth), db=Depends(get_db)):
    s.guard(db, agent.company_id)
    row = get_sync(db, agent, identity)
    values = [v.model_dump() for v in payload.entries]
    checksum = c.part(db, "directory", row.id, number, row.part_count, values)
    db.commit(); return {"digest": checksum}


@router.post("/agent/environment-syncs/{identity}/commit")
def sync_commit(identity: int, agent=Depends(agent_auth), db=Depends(get_db)):
    s.guard(db, agent.company_id); s.enabled(db, agent.company_id)
    permissions.require_access(db, db.get(User, agent.user_id))
    row = get_sync(db, agent, identity)
    if row.status == "committed": return {"status": row.status}
    device = db.get(MatrixDevice, agent.id)
    if not device or device.hub_identity != row.hub_identity: s.fail("同步期间Hub身份发生变化")
    latest = db.scalar(select(func.max(MatrixSync.version)).where(MatrixSync.agent_id == agent.id, MatrixSync.status == "committed"))
    if latest is not None and row.version <= latest: s.fail("旧目录快照拒绝提交")
    entries = c.parts(db, "directory", row.id, row.part_count)
    if len(entries) != row.expected_count or len({e["container_code"] for e in entries}) != len(entries): s.fail("目录数量或分页完整性错误", 422)
    for access in db.scalars(select(MatrixAccess).where(MatrixAccess.agent_id == agent.id)): access.available = False
    for value in entries:
        env = db.scalar(select(MatrixEnvironment).where(MatrixEnvironment.company_id == agent.company_id, MatrixEnvironment.hub_identity == row.hub_identity, MatrixEnvironment.container_code == value["container_code"]))
        values = {"name": value["name"], "group_name": value["group_name"], "serial": value["serial"], "account_names": value["account_names"]}
        if value["site"]: values["observed_site"] = value["site"]
        if not env:
            env = MatrixEnvironment(company_id=agent.company_id, hub_identity=row.hub_identity, container_code=value["container_code"], **values)
            db.add(env); db.flush()
        else:
            changed = any(getattr(env,k) != v for k,v in values.items())
            for k,v in values.items(): setattr(env,k,v)
            if changed: env.revision += 1
        env.observed_at = s.utcnow()
        access = db.scalar(select(MatrixAccess).where(MatrixAccess.agent_id == agent.id, MatrixAccess.environment_id == env.id))
        if not access:
            access = MatrixAccess(agent_id=agent.id, environment_id=env.id); db.add(access)
        access.available, access.seen_at = True, s.utcnow()
    row.status, device.sync_at = "committed", s.utcnow()
    db.commit(); return {"status": row.status, "count": len(entries)}


@router.get("/plan-environments")
def plan_environments(agent_id: int = Query(gt=0), actor=Depends(matrix_user), db=Depends(get_db)):
    agent = db.get(HubAgent, agent_id)
    if not agent or agent.company_id != actor.company_id or agent.user_id != actor.id or not agent.is_active:
        s.fail("请选择自己的执行设备", 422)
    query = s.environment_query(db, actor, {"agent_id": agent_id})
    shops = {shop.id: shop.name for shop in db.scalars(select(MatrixShop).where(MatrixShop.company_id == actor.company_id))}
    return {"items": [{"id": env.id, "name": env.name, "container_code": env.container_code,
        "group": env.group_name, "shop_name": shops.get(env.shop_id), "account_names": env.account_names}
        for env in db.scalars(query)]}


@router.get("/environments")
def environments(q: str = "", site: str = "", group: str = "", agent_id: int | None = None, status: str = "", collection: str = "", exact: str = "", executable: str = "", ungrouped: bool = False,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), actor=Depends(matrix_user), db=Depends(get_db)):
    filters = {"q": q, "site": site, "group": group, "ungrouped": ungrouped, "agent_id": agent_id, "status": status, "collection": collection, "executable": executable, "exact": exact.splitlines() if exact else []}
    query = s.environment_query(db, actor, filters)
    count = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
    envs = db.scalars(query.offset((page-1)*page_size).limit(page_size)).all()
    exact_values = filters["exact"]
    matches = {}
    if exact_values:
        for env in db.scalars(query):
            for v in exact_values:
                if v in {env.name, env.container_code, env.serial}: matches.setdefault(v, []).append(env.id)
    groups = db.scalars(s.environment_query(db, actor).order_by(None).with_only_columns(MatrixEnvironment.group_name).distinct().order_by(MatrixEnvironment.group_name)).all()
    return {"groups": groups, "items": [s.env_view(db,e,actor) for e in envs], "total": count, "page": page, "page_size": page_size,
        "unmatched": [v for v in exact_values if v not in matches], "duplicates": {v: ids for v,ids in matches.items() if len(ids)>1}}


@router.patch("/environments/{identity}/overrides")
def override(identity: int, payload: Override, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db, actor.company_id)
    env = db.scalar(s.environment_query(db, actor).where(MatrixEnvironment.id == identity))
    if not env: s.fail("环境不存在",404)
    if payload.expected_revision != env.revision: s.fail("环境已修改，请刷新")
    s.audit(db, actor, "environment.site", identity, {"before":env.override_site,"after":payload.site,"reason":payload.reason})
    env.override_site, env.revision = payload.site, env.revision+1
    db.commit(); return {"revision":env.revision}


@router.patch("/environments/overrides")
def batch_override(payload: BatchOverride, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db, actor.company_id)
    fields = payload.model_fields_set & {"site", "activity_status"}
    if not fields or ("activity_status" in fields and payload.activity_status is None): s.fail("请选择要修改的站点或活跃状态",422)
    expected={t.id:t.expected_revision for t in payload.environments}
    if len(expected)!=len(payload.environments):s.fail("环境不能重复",422)
    rows=db.scalars(s.environment_query(db,actor).where(MatrixEnvironment.id.in_(expected))).all()
    if len(rows)!=len(expected):s.fail("部分环境已不可访问",404)
    if any(row.revision!=expected[row.id] for row in rows):s.fail("部分环境已修改，整批未保存；请刷新后重新选择")
    for row in rows:
        for field in sorted(fields):
            attr = "override_site" if field == "site" else field
            value = getattr(payload, field)
            s.audit(db,actor,"environment."+field,row.id,{"before":getattr(row,attr),"after":value,"reason":payload.reason})
            setattr(row,attr,value)
        row.revision += 1
    db.commit();return {"items":[{"id":row.id,"revision":row.revision} for row in rows]}


@router.post("/manual/preview")
def manual_preview(payload: ManualPreviewInput, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.manual_preview(db, actor, payload)


@router.post("/manual/runs")
def manual_runs(payload: ManualRunsInput, request: Request, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.manual_runs(db, actor, payload, request.headers.get("Idempotency-Key"))


@router.get("/operations")
def operations(actor=Depends(matrix_user), db=Depends(get_db)):
    rows = db.scalars(select(MatrixOperation).where(MatrixOperation.company_id==actor.company_id, MatrixOperation.owner_id==actor.id, MatrixOperation.deleted.is_(False)).order_by(MatrixOperation.id))
    plans = db.scalars(select(MatrixPlan).where(MatrixPlan.company_id==actor.company_id, MatrixPlan.owner_id==actor.id, MatrixPlan.deleted.is_(False))).all()
    return [{**s.operation_view(row), "plans": [{"id": p.id, "name": p.name} for p in plans if p.config["operation_id"]==row.id]} for row in rows]


@router.post("/operations")
def operation_create(payload: OperationInput, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.save_operation(db, actor, payload)


@router.patch("/operations/{identity}")
def operation_update(identity: int, payload: OperationInput, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.save_operation(db, actor, payload, identity)


@router.delete("/operations/{identity}")
def operation_delete(identity: int, expected_revision: int, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db, actor.company_id)
    operation = s.get_operation(db, actor, identity)
    if operation.revision != expected_revision: s.fail("操作方案已修改，请刷新后重试")
    plans = db.scalars(select(MatrixPlan).where(MatrixPlan.company_id==actor.company_id, MatrixPlan.owner_id==actor.id, MatrixPlan.deleted.is_(False)))
    if any(p.config["operation_id"]==identity for p in plans): s.fail("操作方案仍被运营计划引用，请先调整或删除相关计划")
    operation.deleted = True
    s.audit(db, actor, "operation.delete", identity, {})
    db.commit()
    return {"deleted": True}


@router.post("/operations/{identity}/preview")
def operation_preview(identity: int, payload: OperationPreviewInput, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.preview(db, actor, None, payload, operation_id=identity)


@router.post("/operations/{identity}/runs")
def operation_run(identity: int, payload: RunInput, request: Request, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.create_run(db, actor, None, payload, request.headers.get("Idempotency-Key"), operation_id=identity)


@router.get("/plans")
def plans(actor=Depends(matrix_user), db=Depends(get_db)):
    result=[]
    for plan in db.scalars(select(MatrixPlan).where(MatrixPlan.company_id == actor.company_id, MatrixPlan.owner_id == actor.id, MatrixPlan.deleted.is_(False)).order_by(MatrixPlan.id)):
        fire=db.scalar(select(MatrixFire).where(MatrixFire.plan_id==plan.id).order_by(MatrixFire.fire_at.desc()).limit(1))
        operation = s.get_operation(db, actor, plan.config["operation_id"])
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        hour, minute = map(int, plan.config["time"].split(":"))
        next_fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_fire <= now: next_fire += timedelta(days=1)
        result.append({**s.plan_view(plan), "operation_name": operation.name, "tasks": operation.config["tasks"],
            "next_fire_at": next_fire if plan.config["scheduled"] else None,
            "last_fire":{"status":fire.status,"fire_at":s.instant(fire.fire_at),"run_id":fire.run_id} if fire else None})
    return result


@router.post("/plans")
def plan_create(payload: PlanInput, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.save_plan(db, actor, payload)


@router.patch("/plans/{identity}")
def plan_update(identity: int, payload: PlanInput, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.save_plan(db, actor, payload, identity)


@router.delete("/plans/{identity}")
def plan_delete(identity: int, expected_revision: int, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db, actor.company_id)
    row = s.owned(db, MatrixPlan, identity, actor, "owner_id")
    if row.revision != expected_revision: s.fail("运营计划已修改")
    row.deleted = True; s.audit(db, actor,"plan.delete",identity,{}); db.commit(); return {"deleted":True}


@router.post("/plans/{identity}/preview")
def preview(identity: int, payload: Input, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.preview(db, actor, identity, payload)


@router.post("/plans/{identity}/runs")
def create_run(identity: int, payload: RunInput, request: Request, actor=Depends(matrix_user), db=Depends(get_db)):
    return s.create_run(db, actor, identity, payload, request.headers.get("Idempotency-Key"))


def history_items(db, actor, environment_id):
    env = db.scalar(s.environment_query(db, actor).where(MatrixEnvironment.id == environment_id))
    if not env: s.fail("环境不存在", 404)
    # 包括识别店铺前失败的执行，以及同一稳定店铺在其他环境中的执行。
    condition = MatrixItem.environment_id == environment_id
    if env.shop_id: condition = or_(condition, MatrixItem.shop_id == env.shop_id)
    return select(MatrixItem.id).join(MatrixRun, MatrixRun.id == MatrixItem.run_id).where(MatrixItem.company_id == actor.company_id, MatrixRun.owner_id == actor.id, condition)


@router.get("/runs")
def runs(page: int = Query(1,ge=1), page_size: int = Query(20,ge=1,le=50), environment_id: int | None = Query(None,gt=0), actor=Depends(matrix_user), db=Depends(get_db)):
    query = select(MatrixRun).where(MatrixRun.company_id == actor.company_id)
    query=query.where(MatrixRun.owner_id == actor.id)
    item_ids = history_items(db, actor, environment_id) if environment_id else None
    if item_ids is not None:
        query = query.where(MatrixRun.id.in_(select(MatrixItem.run_id).where(MatrixItem.id.in_(item_ids))))
    subquery = query.with_only_columns(MatrixRun.status).subquery()
    summary = dict(db.execute(select(subquery.c.status, func.count()).group_by(subquery.c.status)).all())
    # 大型冻结货盘 JSON 不参与 MySQL 排序；只按 ID 分页，再按主键读取整条记录。
    ids = query.with_only_columns(MatrixRun.id)
    active_id = db.scalar(ids.where(MatrixRun.status.in_(["running", "queued", "awaiting_attention"])).order_by(MatrixRun.id).limit(1))
    active = db.get(MatrixRun, active_id) if active_id is not None else None
    page_ids = list(db.scalars(ids.order_by(MatrixRun.id.desc()).offset((page-1)*page_size).limit(page_size)))
    records = {row.id: row for row in db.scalars(query.where(MatrixRun.id.in_(page_ids)))} if page_ids else {}
    return {"items":[s.run_view(db,records[identity],item_ids) for identity in page_ids if identity in records],
        "total":db.scalar(select(func.count()).select_from(subquery)), "summary":summary, "active":s.run_view(db,active,item_ids) if active else None}


@router.get("/runs/{identity}")
def run_detail(identity:int, item_id:int | None=Query(None,gt=0), actor=Depends(matrix_user), db=Depends(get_db)):
    run = s.run_access(db,actor,identity)
    if item_id and not db.scalar(select(MatrixItem.id).where(MatrixItem.id==item_id,MatrixItem.run_id==identity)): s.fail("执行项不存在",404)
    return s.run_view(db,run,{item_id} if item_id else None)


@router.get("/runs/{identity}/events")
def events(identity:int, after_seq:int=Query(0,ge=0), item_id:int | None=Query(None,gt=0), actor=Depends(matrix_user), db=Depends(get_db)):
    s.run_access(db,actor,identity)
    attempts = {a.id:a for a in db.scalars(select(MatrixAttempt).join(MatrixItem,MatrixItem.id==MatrixAttempt.item_id).where(MatrixItem.run_id==identity))}
    query = select(MatrixEvent).where(MatrixEvent.run_id==identity,MatrixEvent.seq>after_seq)
    if item_id:
        if not db.scalar(select(MatrixItem.id).where(MatrixItem.id==item_id,MatrixItem.run_id==identity)): s.fail("执行项不存在",404)
        query = query.where(or_(MatrixEvent.attempt_id.in_([a.id for a in attempts.values() if a.item_id==item_id]), MatrixEvent.payload["item_id"].as_integer()==item_id))
    return [{"seq":r.seq,"kind":r.kind,"payload":r.payload,"created_at":s.instant(r.created_at),
        "item_id":attempts[r.attempt_id].item_id if r.attempt_id in attempts else r.payload.get("item_id"),
        "attempt_number":attempts[r.attempt_id].number if r.attempt_id in attempts else None}
        for r in db.scalars(query.order_by(MatrixEvent.seq).limit(500))]


@router.post("/runs/{identity}/stop")
def stop(identity:int, actor=Depends(matrix_user), db=Depends(get_db)):
    s.guard(db,actor.company_id); run=s.run_access(db,actor,identity,manage=True)
    run.stop_requested=True
    for item in db.scalars(select(MatrixItem).where(MatrixItem.run_id==identity)):
        if item.status=="queued": item.status,item.stage="cancelled","cancelled"
    db.add(MatrixCommand(company_id=actor.company_id,agent_id=run.agent_id,kind="stop",payload={"run_id":run.id},expires_at=s.utcnow()+timedelta(minutes=5)))
    s.audit(db,actor,"run.stop",identity,{}); s.recompute(db,run); db.commit(); return {"status":"stop_requested"}


@router.get("/agent/queue")
def queue(agent=Depends(agent_auth), db=Depends(get_db)):
    s.sweep(db, agent.company_id)
    conf=db.get(MatrixCompany,agent.company_id); device=db.get(MatrixDevice,agent.id)
    if not conf or not conf.enabled or not device or device.paused: return {"items":[]}
    query=select(MatrixItem).join(MatrixRun, MatrixRun.id==MatrixItem.run_id).where(MatrixItem.agent_id==agent.id,MatrixRun.owner_id==agent.user_id,MatrixItem.status=="queued",MatrixRun.stop_requested.is_(False)).order_by(MatrixItem.id).limit(20)
    owner = db.get(User, agent.user_id)
    return {"items":[s.item_view(i) for i in db.scalars(query) if permissions.tasks_allowed(db, owner, db.get(MatrixRun, i.run_id).frozen["config"]["tasks"])]}


@router.post("/agent/items/{identity}/claim")
def claim(identity:int, agent=Depends(agent_auth), db=Depends(get_db)):
    return s.claim(db,agent,identity)


@router.post("/agent/items/{identity}/renew")
def renew(identity:int,payload:AttemptInput,agent=Depends(agent_auth),db=Depends(get_db)):
    item,attempt,run=s.checked_attempt(db,agent,identity,payload)
    stopping=run.stop_requested or not permissions.tasks_allowed(db,db.get(User,agent.user_id),run.frozen["config"]["tasks"])
    # 停止或收回权限后，仅保留现有租约供结果收尾，不能无限续租。
    if not stopping:attempt.lease_until=s.utcnow()+timedelta(seconds=90)
    if item.upload_task_id:
        task=db.get(HubUploadTask,item.upload_task_id)
        if task.status=="running":task.lease_expires_at=attempt.lease_until
    remaining=max(0,int((attempt.lease_until-s.utcnow()).total_seconds()))
    db.commit(); return {"stop_requested":stopping,"lease_seconds":remaining}


@router.post("/agent/items/{identity}/events")
def append_event(identity:int,payload:EventInput,agent=Depends(agent_auth),db=Depends(get_db)):
    item,attempt,run=s.checked_attempt(db,agent,identity,payload)
    s.event(db,item,"progress",{"stage":payload.stage,"message":payload.message},payload.source_id)
    item.stage=payload.stage; db.commit(); return {"persisted":True}


@router.post("/agent/items/{identity}/identity")
def bind_identity(identity:int,payload:IdentityInput,agent=Depends(agent_auth),db=Depends(get_db)):
    item,attempt,run=s.checked_attempt(db,agent,identity,payload)
    permissions.require_tasks(db,db.get(User,agent.user_id),run.frozen["config"]["tasks"])
    return s.bind_identity(db,agent,identity,payload)


@router.post("/agent/items/{identity}/environment-target")
def bind_environment_target(identity:int,payload:AttemptInput,agent=Depends(agent_auth),db=Depends(get_db)):
    return s.bind_environment_target(db,agent,identity,payload)


@router.post("/agent/items/{identity}/listing-preparations")
def prepare(identity:int,payload:AttemptInput,agent=Depends(agent_auth),db=Depends(get_db)):
    item,attempt,run=s.checked_attempt(db,agent,identity,payload)
    permissions.require_tasks(db,db.get(User,agent.user_id),run.frozen["config"]["tasks"])
    return listing.prepare(db,agent,identity,payload)


@router.post("/agent/items/{identity}/file")
def file(identity:int,payload:AttemptInput,agent=Depends(agent_auth),db=Depends(get_db)):
    item,attempt,run=s.checked_attempt(db,agent,identity,payload)
    permissions.require_tasks(db,db.get(User,agent.user_id),run.frozen["config"]["tasks"])
    return Response(listing.download(db,agent,identity,payload),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.post("/agent/items/{identity}/submission")
def submission(identity:int,payload:AttemptInput,agent=Depends(agent_auth),db=Depends(get_db)):
    item,attempt,run=s.checked_attempt(db,agent,identity,payload)
    permissions.require_tasks(db,db.get(User,agent.user_id),run.frozen["config"]["tasks"])
    return listing.submission(db,agent,identity,payload)


@router.post("/agent/items/{identity}/listing-result")
def listing_result(identity:int,payload:ListingResult,agent=Depends(agent_auth),db=Depends(get_db)):
    return listing.confirm(db,agent,identity,payload)


@router.post("/agent/items/{identity}/report")
def report(identity:int,payload:Report,agent=Depends(agent_auth),db=Depends(get_db)):
    return s.report(db,agent,identity,payload)


@router.post("/agent/items/{identity}/collections")
def create_collection(identity:int,payload:CollectionInput,agent=Depends(agent_auth),db=Depends(get_db)):
    row=c.create(db,agent,identity,payload); db.commit(); return {"id":row.id,"status":row.status}


@router.put("/agent/items/{identity}/collections/{cid}/parts/{number}")
def collection_part(identity:int,cid:int,number:int,payload:CollectionPart,agent=Depends(agent_auth),db=Depends(get_db)):
    s.checked_attempt(db,agent,identity,payload)
    row=db.get(MatrixCollection,cid)
    if not row or row.item_id!=identity or row.company_id!=agent.company_id:s.fail("采集包不存在",404)
    checksum=c.part(db,"collection",cid,number,row.part_count,[p.model_dump(exclude_unset=True) for p in payload.products])
    db.commit();return {"digest":checksum}


@router.post("/agent/items/{identity}/collections/{cid}/commit")
def commit_collection(identity:int,cid:int,payload:AttemptInput,agent=Depends(agent_auth),db=Depends(get_db)):
    return c.commit(db,agent,identity,cid,payload)


@router.post("/run-items/{identity}/resolve")
def resolve(identity:int,payload:Resolve,actor=Depends(matrix_user),db=Depends(get_db)):
    s.guard(db,actor.company_id)
    item=s.owned(db,MatrixItem,identity,actor);run=s.run_access(db,actor,item.run_id,manage=True)
    if item.status not in {"awaiting_attention","failed","partial_success"}:s.fail("当前状态不能人工处理")
    if payload.action=="confirm-submitted":
        if not item.upload_task_id:s.fail("没有可确认的上品文件")
        if item.submission not in {'request_sent','unknown'}:s.fail('仅结果未知的提交可以人工确认，明确未提交项不能改记成功')
        has_rejections=listing.manual_confirmation(db,item,payload.evidence)
        item.submission="confirmed"
        task=db.get(HubUploadTask,item.upload_task_id)
        task.status,task.stage,task.completed_at,task.claim_token,task.lease_expires_at="completed","manually_confirmed",s.utcnow(),None,None
        hub.finish_attempt(db,task,'completed')
        item.status="succeeded" if not has_rejections and ("shop.collect" not in run.frozen["config"]["tasks"] or item.collection_status=="committed") else "partial_success"
    elif payload.action=="confirm-not-submitted":
        if not item.upload_task_id or item.submission not in {"request_sent","unknown"}:s.fail("仅结果未知的上品可以核对为未提交")
        if item.result.get("listing",{}).get("accepted") or db.scalar(select(MatrixAllocation.id).where(MatrixAllocation.item_id==identity,MatrixAllocation.state=="confirmed")):
            s.fail("已有商品确认提交，不能将整份文件确认为未提交")
        task=db.get(HubUploadTask,item.upload_task_id)
        if not task:s.fail("原上品记录不存在")
        task.status,task.stage,task.completed_at,task.claim_token,task.lease_expires_at="cancelled","manually_not_submitted",s.utcnow(),None,None
        task.resolved_by,task.resolved_at=actor.id,s.utcnow()
        hub.finish_attempt(db,task,'cancelled')
        item.status,item.stage,item.submission="cancelled","manually_not_submitted","not_started"
        item.result={**item.result,"manual_not_submitted":payload.evidence}
        for allocation in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id==identity,MatrixAllocation.state!="confirmed")):allocation.state="released"
    elif payload.action in {"retry","retransmit"}:
        if run.owner_id!=actor.id:s.fail("仅任务所有者可重新执行",403)
        if run.stop_requested:s.fail("该运行已停止，请创建新运行")
        permissions.require_tasks(db,actor,run.frozen["config"]["tasks"])
        if payload.action=="retry" and item.submission=="confirmed":s.fail("上品已确认完成，禁止重新导入；可重传原采集包或新建纯采集运行")
        if payload.action=="retry":listing.reserve_retry(db,item)
        if payload.action=="retry" and item.upload_task_id:
            task=db.get(HubUploadTask,item.upload_task_id);hub.require_file(task)
            item.submission="not_started"; task.status,task.stage,task.claim_token,task.lease_expires_at="queued","queued",None,None
            item.result={k:v for k,v in item.result.items() if k not in {"retransmit_only", "listing"}}
        if payload.action=="retransmit":
            if not db.scalar(select(MatrixCollection.id).where(MatrixCollection.item_id==identity)):s.fail("没有持久化采集包")
            item.result={**item.result,"retransmit_only":True}
        item.status,item.stage,item.error="queued","queued",None
    else:
        if item.submission in {"request_sent","unknown"}:s.fail("提交结果未知，须先核对已提交或未提交")
        item.status,item.stage="cancelled","cancelled"
        for row in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id == identity, MatrixAllocation.state.in_(["reserved", "prepared"]))): row.state = "released"
    s.release_guard(db,item)
    s.audit(db,actor,"item."+payload.action,identity,{"evidence":payload.evidence})
    s.event(db,item,"manual.resolve",{"action":payload.action,"evidence":payload.evidence})
    s.recompute(db,run);db.commit();return s.item_view(item)


@router.get("/shops/metrics")
def metrics(q:str="",site:str="",group:str="",agent_id:int|None=None,status:str="",collection:str="",exact:str="",executable:str="",ungrouped:bool=False,actor=Depends(matrix_user),db=Depends(get_db)):
    envs=db.scalars(s.environment_query(db,actor,{"q":q,"site":site,"group":group,"ungrouped":ungrouped,"agent_id":agent_id,"status":status,"collection":collection,"executable":executable,"exact":exact.splitlines() if exact else []}).limit(20001)).all()
    if len(envs)>20000:s.fail("环境数量超过汇总上限",413)
    unique={}
    for env in envs:
        if env.shop_id:unique[env.shop_id]=env
    snapshots=[]
    for env in unique.values():
        snapshot=s.own_snapshot(db,actor,env.shop_id)
        if snapshot:snapshots.append(c.snapshot_view(db,snapshot))
    groups={}
    for snap in snapshots:
        if snap["window_start"] is None or snap["window_end"] is None: continue
        key=(snap["site"],snap["window_start"],snap["window_end"])
        bucket=groups.setdefault(key,{"site":key[0],"window_start":key[1],"window_end":key[2],"shops":0,"impressions":None,"clicks":None,"covered":0,"traffic_covered":0,"traffic_unknown":0})
        bucket["shops"]+=1
        bucket["traffic_covered"]+=snap.get("traffic_covered",0)
        bucket["traffic_unknown"]+=snap.get("traffic_unknown",0)
        if snap["impressions"] is not None and snap["clicks"] is not None:
            bucket["impressions"]=(bucket["impressions"] or 0)+snap["impressions"];bucket["clicks"]=(bucket["clicks"] or 0)+snap["clicks"];bucket["covered"]+=1
    for bucket in groups.values():bucket["ctr"]=bucket["clicks"]/bucket["impressions"] if bucket["impressions"] else None
    return {"total":len(envs),"collected":len(snapshots),"active":sum(v["active"] for v in snapshots) if snapshots else None,
        "views":sum(v["views"] for v in snapshots) if snapshots and all(v.get("views") is not None for v in snapshots) else None,
        "with_views":sum(v["with_views"] for v in snapshots) if snapshots and all(v.get("with_views") is not None for v in snapshots) else None,
        "zero_views":sum(v["zero_views"] for v in snapshots) if snapshots and all(v.get("zero_views") is not None for v in snapshots) else None,
        "sku_count":sum(v["sku_count"] for v in snapshots) if snapshots and all(v.get("sku_count") is not None for v in snapshots) else None,
        "with_impressions":sum(v["with_impressions"] for v in snapshots) if snapshots and all(v["with_impressions"] is not None for v in snapshots) else None,
        "zero_impressions":sum(v["zero_impressions"] for v in snapshots) if snapshots and all(v["zero_impressions"] is not None for v in snapshots) else None,
        "violations":sum(Decimal(str(v.get("violations_score") or 0))>0 for v in snapshots),
        "violations_covered":sum(v.get("violations_score") is not None for v in snapshots),"windows":list(groups.values())}


@router.get("/shops/{identity}/snapshots")
def snapshots(identity:int,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),q:str="",actor=Depends(matrix_user),db=Depends(get_db)):
    if not db.scalar(s.environment_query(db,actor).where(MatrixEnvironment.shop_id==identity).limit(1)):s.fail("店铺不存在",404)
    row=s.own_snapshot(db,actor,identity)
    if not row:return {"snapshot":None,"products":[],"total":0}
    values=[p for part in db.scalars(select(MatrixPart).where(MatrixPart.kind=="collection",MatrixPart.parent_id==row.id).order_by(MatrixPart.number)) for p in part.payload if not q or q.casefold() in (p["name"]+p["external_id"]).casefold()]
    return {"snapshot":c.snapshot_view(db,row),"products":values[(page-1)*page_size:page*page_size],"total":len(values)}


def csv_value(value):
    text="" if value is None else str(value)
    return "'"+text if text.lstrip().startswith(("=","+","-","@","\t","\r")) else text


@router.get("/shops/{identity}/export")
def shop_export(identity:int,q:str="",actor=Depends(matrix_user),db=Depends(get_db)):
    # 复用详情的权限边界；导出固定当前快照和当前商品搜索范围。
    view=snapshots(identity,page=1,page_size=100,q=q,actor=actor,db=db)
    snapshot=view['snapshot']
    if not snapshot:s.fail("店铺尚无有效快照",404)
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["商品ID","商品名称","在售","浏览次数","浏览次数说明","SKU数量","SKU ID","SKU规格","商家SKU","SKU库存","SKU原价","SKU促销价","币种","采集时间","曝光","点击","窗口开始","窗口结束","成交件数","分析数据说明","GMV","GMV币种"])
    count=0
    for part in db.scalars(select(MatrixPart).where(MatrixPart.kind=="collection",MatrixPart.parent_id==snapshot['id']).order_by(MatrixPart.number)):
        for product in part.payload:
            if q and q.casefold() not in (product['name']+product['external_id']).casefold():continue
            for sku in product.get('skus') or [{}]:
                writer.writerow([csv_value(v) for v in [product['external_id'],product['name'],product.get('active',True),product.get('views'),product.get('views_reason'),product.get('sku_count'),
                    sku.get('external_id'),sku.get('name'),sku.get('seller_sku'),sku.get('stock'),sku.get('price'),sku.get('sale_price'),sku.get('currency',snapshot['currency']),
                    snapshot['observed_at'],product.get('impressions'),product.get('clicks'),snapshot['window_start'],snapshot['window_end'],product.get('sales_count'),product.get('traffic_reason'),product.get('gmv'),snapshot['currency']]])
            count+=1
    s.audit(db,actor,"shop.export",identity,{"snapshot_id":snapshot['id'],"count":count});db.commit()
    return Response("\ufeff"+output.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":"attachment; filename=tk-shop-products.csv"})


@router.get("/exports")
def export(q:str="",site:str="",group:str="",agent_id:int|None=None,status:str="",collection:str="",exact:str="",executable:str="",ungrouped:bool=False,actor=Depends(matrix_user),db=Depends(get_db)):
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(["环境名 / 编号","分组","站点","在售商品","有浏览","零浏览","动销率","曝光","点击","CTR","GMV","7日访客","违规分","采集时间"])
    envs=db.scalars(s.environment_query(db,actor,{"q":q,"site":site,"group":group,"ungrouped":ungrouped,"agent_id":agent_id,"status":status,"collection":collection,"executable":executable,"exact":exact.splitlines() if exact else []}).limit(20001)).all()
    if len(envs)>20000:s.fail("导出超过20000环境",413)
    for env in envs:
        snapshot=s.own_snapshot(db,actor,env.shop_id) if env.shop_id else None
        snap=c.snapshot_view(db,snapshot) if snapshot else {}
        observed = snap.get("observed_at")
        collected_at = datetime.fromisoformat(observed.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Hong_Kong")).strftime("%Y/%m/%d %H:%M:%S") if observed else "未采集"
        writer.writerow([csv_value(v) for v in [f"{env.name}\n{env.container_code}",env.group_name or "未分组",env.override_site or env.observed_site or "未知",
            *[snap.get(k) if snap.get(k) is not None else "—" for k in ("active","with_views","zero_views")],
            f"{snap['sell_through_rate']:.2%}" if snap.get("sell_through_rate") is not None else "—",
            *[snap.get(k) if snap.get(k) is not None else "—" for k in ("impressions","clicks")],
            f"{snap['ctr']:.2%}" if snap.get("ctr") is not None else "—",
            f"{snap['gmv']} {snap['currency']}" if snap.get("gmv") is not None else "—",
            *[snap.get(k) if snap.get(k) is not None else "—" for k in ("visitors7d","violations_score")],collected_at]])
    s.audit(db,actor,"metrics.export",0,{"count":len(envs)});db.commit()
    filename = f"店铺数据-{datetime.now(ZoneInfo('Asia/Hong_Kong')):%Y-%m-%d}.csv"
    return Response("\ufeff"+output.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f"attachment; filename*=UTF-8''{quote(filename)}"})
