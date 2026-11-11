"""矩阵目录、方案与执行状态；所有写事务先取公司协调锁。"""
import base64
import copy
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func, or_, and_, String
from fastapi import HTTPException
from .. import hub
from ..security import validate_supply_user_access
from ..models import Company, User, Role, HubAgent, HubUploadTask, HubRuntimeLock, SupplyStrategy, TiktokCategoryCatalog
from ..supply_common import digest, validate_strategy, eligible_materials, template_version
from ..tiktok_export import catalog_listing_options
from .models import *
from . import permissions

ACTIVE = ("queued", "running", "awaiting_attention")
TERMINAL = ("succeeded", "partial_success", "failed", "cancelled")
MARKETS = {"MY", "ID"}


def utcnow():
    return datetime.utcnow()


def instant(value):
    return value.replace(tzinfo=timezone.utc) if value else None


def fail(message, status=409):
    raise HTTPException(status, message)


def guard(db, company_id):
    transaction = db.get_transaction()
    # 鉴权的普通读可能已建立MySQL快照；首次写锁前结束它。嵌套服务调用保留事务。
    if db.info.get("matrix_write_transaction") is not transaction or transaction is None:
        if db.new or db.dirty or db.deleted:
            raise RuntimeError("矩阵协调锁必须在业务写入之前获取")
        db.rollback()
    company = hub.lock_row(db, Company, company_id)
    db.info["matrix_write_transaction"] = db.get_transaction()
    if not company or not company.is_active:
        fail("公司不可用", 403)
    authenticated = db.info.get("matrix_authenticated")
    if authenticated:
        user = hub.lock_row(db, User, authenticated["user_id"])
        if not user or not user.is_active or user.company_id != company_id or user.role not in permissions.ROLES:
            fail("账号权限已变更", 401)
        validate_supply_user_access(user, db)
        if "token_version" in authenticated:
            if user.token_version != authenticated["token_version"]: fail("登录凭证已失效", 401)
            permissions.require_access(db, user)
        if "agent_id" in authenticated:
            agent = hub.lock_row(db, HubAgent, authenticated["agent_id"])
            if not agent or not agent.is_active or agent.user_id != user.id or agent.company_id != company_id or agent.token_hash != authenticated["token_hash"]:
                fail("设备授权已失效", 401)
    return company


def enabled(db, company_id, listing=False):
    config = db.get(MatrixCompany, company_id)
    if not config or not config.enabled:
        fail("矩阵功能尚未启用" if not listing else "自动上品尚未启用", 403)
    return config


def owned(db, model, identity, actor, owner_field=None):
    row = db.get(model, identity)
    if not row or row.company_id != actor.company_id:
        fail("记录不存在", 404)
    if owner_field and getattr(row, owner_field) != actor.id:
        fail("记录不存在", 404)
    return row


def audit(db, actor, action, identity, payload):
    db.add(MatrixAudit(company_id=actor.company_id, actor_id=actor.id, action=action, subject_id=identity, payload=payload))


def device_view(db, agent):
    device = db.get(MatrixDevice, agent.id)
    owner = db.get(User, agent.user_id)
    return {"id": agent.id, "name": agent.name, "user_id": agent.user_id, "user_name": owner.name if owner else "", "platform": agent.platform,
        "online": bool(agent.is_active and agent.last_seen_at and agent.last_seen_at > utcnow() - timedelta(seconds=45)),
        "last_seen_at": instant(agent.last_seen_at), "version": device.version if device else "协议4", "capabilities": device.capabilities if device else {},
        "hub_identity": device.hub_identity if device else None, "hub_connected": bool(device and device.hub_connected),
        "paused": bool(device and (device.paused or device.local_paused)), "sync_at": instant(device.sync_at) if device else None,
        "update_state": device.update_state if device else {}, "is_active": agent.is_active,
        "permissions": permissions.access(db, owner)}


def accessible_ids(db, actor, agent_id=None):
    query = select(MatrixAccess.environment_id).join(HubAgent, HubAgent.id == MatrixAccess.agent_id).where(
        MatrixAccess.available.is_(True), HubAgent.company_id == actor.company_id, HubAgent.is_active.is_(True))
    if not permissions.company_view(db, actor):
        query = query.where(HubAgent.user_id == actor.id)
    if agent_id:
        query = query.where(HubAgent.id == agent_id)
    return query


def environment_query(db, actor, filters=None):
    f = dict(filters or {})
    if isinstance(f.get("exact"), str): f["exact"] = f["exact"].splitlines()
    query = select(MatrixEnvironment).where(MatrixEnvironment.company_id == actor.company_id, MatrixEnvironment.id.in_(accessible_ids(db, actor, f.get("agent_id"))))
    if f.get("q"):
        term = str(f["q"])[:200]
        shop_ids = select(MatrixShop.id).where(MatrixShop.company_id == actor.company_id, or_(MatrixShop.name.contains(term, autoescape=True), MatrixShop.external_id.contains(term, autoescape=True)))
        query = query.where(or_(MatrixEnvironment.name.contains(term, autoescape=True), MatrixEnvironment.container_code.contains(term, autoescape=True),
            MatrixEnvironment.serial.contains(term, autoescape=True), MatrixEnvironment.shop_id.in_(shop_ids),
            MatrixEnvironment.id.in_(select(MatrixEnvironment.id).where(MatrixEnvironment.company_id == actor.company_id, MatrixEnvironment.account_names.cast(String).contains(term, autoescape=True)))))
    if f.get("site") == "unknown":
        query = query.where(func.coalesce(MatrixEnvironment.override_site, MatrixEnvironment.observed_site).is_(None))
    elif f.get("site"):
        query = query.where(func.coalesce(MatrixEnvironment.override_site, MatrixEnvironment.observed_site) == f["site"])
    if f.get("executable"):
        company=db.get(MatrixCompany,actor.company_id)
        grant=permissions.access(db,actor)
        capability=or_(*(and_(func.coalesce(MatrixEnvironment.override_site,MatrixEnvironment.observed_site)==site,
            or_(and_(grant['collect_enabled'],MatrixDevice.capabilities['shop.collect'].contains(site)),and_(bool(company and company.enabled and grant['listing_enabled']),MatrixDevice.capabilities['listing.catalog'].contains(site)))) for site in ('MY',)))
        ready=select(MatrixAccess.environment_id).join(HubAgent,HubAgent.id==MatrixAccess.agent_id).join(MatrixDevice,MatrixDevice.agent_id==HubAgent.id).join(MatrixEnvironment,MatrixEnvironment.id==MatrixAccess.environment_id).where(
            MatrixAccess.available.is_(True),MatrixAccess.seen_at>utcnow()-timedelta(minutes=5),HubAgent.company_id==actor.company_id,
            HubAgent.is_active.is_(True),HubAgent.last_seen_at>utcnow()-timedelta(seconds=45),MatrixDevice.hub_connected.is_(True),
            MatrixDevice.paused.is_(False),MatrixDevice.local_paused.is_(False),MatrixDevice.hub_identity==MatrixEnvironment.hub_identity,
            capability,True if actor.role==Role.COMPANY_ADMIN else HubAgent.user_id==actor.id,
            True if not f.get('agent_id') else HubAgent.id==f['agent_id'],
            ~HubAgent.id.in_(select(MatrixItem.agent_id).where(MatrixItem.status=='running')),
            ~HubAgent.id.in_(select(HubUploadTask.agent_id).where(HubUploadTask.status=='running',HubUploadTask.agent_id.is_not(None))),
            ~MatrixEnvironment.container_code.in_(select(HubRuntimeLock.container_code).where(HubRuntimeLock.company_id==actor.company_id,or_(HubRuntimeLock.task_id.is_not(None),HubRuntimeLock.matrix_item_id.is_not(None)))))
        available=MatrixEnvironment.id.in_(ready)
        if not company or not company.enabled:available=MatrixEnvironment.id.in_([])
        query=query.where(available if f['executable']=='ready' else ~available)
    if f.get("ungrouped"):
        query = query.where(MatrixEnvironment.group_name == "")
    elif f.get("group"):
        query = query.where(MatrixEnvironment.group_name == f["group"])
    if f.get("exact"):
        values = list(dict.fromkeys(str(x).strip() for x in f["exact"] if str(x).strip()))[:500]
        query = query.where(or_(MatrixEnvironment.name.in_(values), MatrixEnvironment.container_code.in_(values), MatrixEnvironment.serial.in_(values)))
    latest = select(func.max(MatrixItem.id)).join(MatrixRun, MatrixRun.id == MatrixItem.run_id).where(MatrixItem.company_id == actor.company_id)
    if not permissions.company_view(db, actor): latest = latest.where(MatrixRun.owner_id == actor.id)
    latest = latest.group_by(MatrixItem.environment_id)
    if f.get("status"):
        query = query.where(MatrixEnvironment.id.in_(select(MatrixItem.environment_id).where(MatrixItem.id.in_(latest), MatrixItem.status == f["status"])))
    if f.get("collection"):
        condition = MatrixEnvironment.id.in_(select(MatrixItem.environment_id).where(MatrixItem.id.in_(latest), MatrixItem.collection_status == f["collection"]))
        if f["collection"] == "not_requested":
            condition = or_(condition, ~MatrixEnvironment.id.in_(select(MatrixItem.environment_id).where(MatrixItem.id.in_(latest))))
        query = query.where(condition)
    return query.order_by(MatrixEnvironment.group_name, MatrixEnvironment.name, MatrixEnvironment.id)


def env_view(db, env, actor):
    from .collections import snapshot_view
    agents = db.scalars(select(HubAgent).join(MatrixAccess, MatrixAccess.agent_id == HubAgent.id).where(MatrixAccess.environment_id == env.id,
        MatrixAccess.available.is_(True), HubAgent.company_id == actor.company_id, HubAgent.is_active.is_(True),
        True if permissions.company_view(db, actor) else HubAgent.user_id == actor.id)).all()
    item = db.scalar(select(MatrixItem).where(MatrixItem.environment_id == env.id,
        True if permissions.company_view(db, actor) else MatrixItem.run_id.in_(select(MatrixRun.id).where(MatrixRun.owner_id == actor.id))).order_by(MatrixItem.id.desc()).limit(1))
    shop = db.get(MatrixShop, env.shop_id) if env.shop_id else None
    snap = db.get(MatrixCollection, shop.snapshot_id) if shop and shop.snapshot_id else None
    return {"id": env.id, "name": env.name, "container_code": env.container_code, "serial": env.serial, "group": env.group_name,
        "site": env.override_site or env.observed_site, "site_source": "manual" if env.override_site else "observed", "revision": env.revision,
        "activity_status": env.activity_status or ("normal" if snap and snap.header.get("metrics", {}).get("shop_status") == "normal" else "unchecked"),
        "account_names": env.account_names, "hub_identity": env.hub_identity, "observed_at": instant(env.observed_at),
        "shop": {"id": shop.id, "external_id": shop.external_id, "name": shop.name} if shop else None,
        "devices": [device_view(db, a) for a in agents], "latest_item": item_view(item) if item else None,
        "snapshot": snapshot_view(db, snap) if snap else None}


def item_view(item):
    return {key: getattr(item, key) for key in ("id", "run_id", "environment_id", "agent_id", "status", "stage", "shop_id", "submission", "collection_status", "error", "result", "supply_job_id", "upload_task_id")}


def plan_view(plan):
    return {"id": plan.id, "name": plan.name, "owner_id": plan.owner_id, "agent_id": plan.agent_id, "revision": plan.revision, **plan.config}


def operation_view(operation):
    return {"id": operation.id, "name": operation.name, "revision": operation.revision, **operation.config}


def get_operation(db, actor, identity):
    operation = owned(db, MatrixOperation, identity, actor, "owner_id")
    if operation.deleted: fail("操作方案已删除", 404)
    return operation


def validate_operation(db, actor, config):
    permissions.require_tasks(db, actor, config["tasks"])
    if set(config["strategies"]) - {"MY"}: fail("当前仅支持马来西亚货盘策略", 422)
    for strategy_id in config["strategies"].values():
        strategy = owned(db, SupplyStrategy, strategy_id, actor, "user_id")
        _, catalog, _, _ = validate_strategy(db, actor, copy.deepcopy(strategy.parameters))
        if catalog.template_type != "tiktok_cross_border" or catalog.site != "MY" or strategy.parameters.get('title_site', 'MY') != 'MY':
            fail("自动上品仅支持马来西亚跨境类目库的策略", 422)
    if "listing.catalog" in config["tasks"] and not config["strategies"]:
        fail("请选择站点对应的货盘策略", 422)


def save_operation(db, actor, payload, identity=None):
    guard(db, actor.company_id); enabled(db, actor.company_id)
    operation = get_operation(db, actor, identity) if identity else None
    if operation and operation.revision != payload.expected_revision: fail("操作方案已修改，请刷新后重试")
    config = payload.model_dump(exclude={"name", "expected_revision"})
    validate_operation(db, actor, config)
    if not operation:
        operation = MatrixOperation(company_id=actor.company_id, owner_id=actor.id, name=payload.name, config=config, revision=1)
        db.add(operation); db.flush()
    else:
        operation.name, operation.config, operation.revision = payload.name, config, operation.revision + 1
        # 修改模板使关联计划的旧预览失效，已创建运行继续使用冻结输入。
        for plan in db.scalars(select(MatrixPlan).where(MatrixPlan.company_id==actor.company_id, MatrixPlan.owner_id==actor.id, MatrixPlan.deleted.is_(False))):
            if plan.config["operation_id"] == operation.id:
                plan.revision += 1
                db.add(MatrixPlanVersion(plan_id=plan.id, revision=plan.revision, payload=plan_view(plan)))
    audit(db, actor, "operation.save", operation.id, {"revision": operation.revision})
    db.commit()
    return operation_view(operation)


def scheduled_environment_ids(db, actor, agent_id, config):
    query = environment_query(db, actor, {"agent_id": agent_id}).where(MatrixEnvironment.id.in_(config["environment_ids"]))
    return list(db.scalars(query.with_only_columns(MatrixEnvironment.id)))


def save_plan(db, actor, payload, identity=None):
    guard(db, actor.company_id); enabled(db, actor.company_id)
    plan = owned(db, MatrixPlan, identity, actor, "owner_id") if identity else None
    if plan and (plan.deleted or payload.expected_revision != plan.revision): fail("运营计划已修改，请刷新后重试")
    operation = get_operation(db, actor, payload.operation_id)
    validate_operation(db, actor, operation.config)
    agent = db.get(HubAgent, payload.agent_id)
    device = db.get(MatrixDevice, payload.agent_id)
    if not agent or agent.company_id != actor.company_id or agent.user_id != actor.id or not agent.is_active or not device:
        fail("请选择自己已注册协议5的设备", 422)
    config = payload.model_dump(exclude={"name", "agent_id", "expected_revision"})
    if set(scheduled_environment_ids(db, actor, agent.id, config)) != set(config["environment_ids"]):
        fail("所选店铺已不可用或不属于执行设备，请重新选择", 422)
    if not plan:
        plan = MatrixPlan(company_id=actor.company_id, owner_id=actor.id, agent_id=agent.id, name=payload.name, config=config, revision=1)
        db.add(plan); db.flush()
    else:
        plan.name, plan.agent_id, plan.config, plan.revision, plan.updated_at = payload.name, agent.id, config, plan.revision + 1, utcnow()
    db.add(MatrixPlanVersion(plan_id=plan.id, revision=plan.revision, payload=plan_view(plan)))
    audit(db, actor, "plan.save", plan.id, {"revision": plan.revision})
    db.commit()
    return plan_view(plan)


def freeze_strategy(db, actor, strategy_id):
    strategy = owned(db, SupplyStrategy, strategy_id, actor, "user_id")
    parameters = copy.deepcopy(strategy.parameters)
    template, catalog, snapshot, rows = validate_strategy(db, actor, parameters)
    if catalog.template_type != "tiktok_cross_border" or catalog.site != "MY" or parameters.get('title_site', 'MY') != 'MY':
        fail("自动上品仅支持马来西亚跨境类目库的策略", 422)
    version = template_version(snapshot)
    candidates = eligible_materials(db, actor.company_id, template.id, version, parameters.get("infringement_filter", "include"))
    if len(candidates) > 20000: fail("单站点候选素材超过20000条，请缩小公开货盘模板范围", 422)
    return {"strategy_id": strategy.id, "name": strategy.name, "parameters": parameters, "template": snapshot, "template_version": version,
        "catalog_type": catalog.template_type, "catalog_site": catalog.site, "catalog_options": copy.deepcopy(catalog_listing_options(catalog)), "category_blob": base64.b64encode(catalog.template_blob).decode(), "candidates": candidates, "expected_rows": rows}


def preview(db, actor, plan_id, payload, operation_id=None, manual_config=None, manual_agent_id=None, commit=True):
    guard(db, actor.company_id); enabled(db, actor.company_id)
    plan = owned(db, MatrixPlan, plan_id, actor, "owner_id") if plan_id else None
    if plan and plan.deleted: fail("运营计划已删除", 404)
    operation = get_operation(db, actor, plan.config["operation_id"] if plan else operation_id) if plan or operation_id else None
    config = operation.config if operation else manual_config
    revision = plan.revision if plan else operation.revision if operation else 1
    permissions.require_tasks(db, actor, config["tasks"])
    agent_id = plan.agent_id if plan else manual_agent_id or payload.agent_id
    device = db.get(MatrixDevice, agent_id)
    agent = db.get(HubAgent, agent_id)
    if not device or not agent or not agent.is_active or agent.company_id != actor.company_id or agent.user_id != actor.id: fail("设备授权已变更")
    # 计划立即运行和定时触发始终使用同一份固定名单。
    target_ids = plan.config["environment_ids"] if plan else payload.environment_ids
    all_filtered = not plan and payload.all_filtered
    f = {**({} if plan else payload.filters.model_dump()), "agent_id": agent_id}
    query = environment_query(db, actor, f)
    if all_filtered:
        selected_ids = list(db.scalars(environment_query(db, actor, payload.filters.model_dump()).with_only_columns(MatrixEnvironment.id).limit(1001)))
        if len(selected_ids) > 1000: fail("请选择1至1000个有权环境", 422)
        available_ids = set(db.scalars(query.with_only_columns(MatrixEnvironment.id)))
        if not set(selected_ids) <= available_ids: fail("所选环境不全部属于执行设备，请按设备筛选后重试", 422)
    if not all_filtered: query = query.where(MatrixEnvironment.id.in_(target_ids))
    envs = db.scalars(query.limit(1001)).all()
    if not envs or len(envs) > 1000: fail("请选择1至1000个有权环境", 422)
    if not all_filtered and set(target_ids) != {e.id for e in envs}: fail("所选环境不再可用")
    errors, summaries, strategies = [], [], {}
    if not agent.last_seen_at or agent.last_seen_at<utcnow()-timedelta(seconds=45):errors.append('执行设备离线')
    if not device.hub_connected:errors.append('HubStudio连接异常')
    if device.paused or device.local_paused:errors.append('执行设备已暂停领取')
    for env in envs:
        site = env.override_site or env.observed_site
        if site not in MARKETS: errors.append(f"{env.name}：站点未确认")
        elif site != 'MY': errors.append(f"{env.name}：当前仅支持马来西亚（MY）跨境店")
        if env.hub_identity != device.hub_identity: errors.append(f"{env.name}：Hub身份不匹配")
        access=db.scalar(select(MatrixAccess).where(MatrixAccess.agent_id==agent.id,MatrixAccess.environment_id==env.id))
        if not access or access.seen_at<utcnow()-timedelta(minutes=5):errors.append(f'{env.name}：目录已过期，请同步环境')
        for task in config["tasks"]:
            if site in MARKETS and site not in device.capabilities.get(task, []):
                market = {"MY": "马来西亚", "ID": "印尼"}[site]
                action = {"shop.collect": "店铺采集", "listing.catalog": "自动上品"}[task]
                errors.append(f"{env.name}：连接器暂未提供{market}站{action}能力，请更新或重启连接器后重试")
        if "listing.catalog" in config["tasks"]:
            enabled(db, actor.company_id, listing=True)
            sid = config.get("strategies", {}).get(site)
            if not sid: errors.append(f"{env.name}：缺少站点货盘策略")
            elif site not in strategies: strategies[site] = freeze_strategy(db, actor, sid)
        summaries.append({"id": env.id, "name": env.name, "site": site, "revision": env.revision, "container_code": env.container_code, "hub_identity": env.hub_identity})
    raw = secrets.token_urlsafe(32)
    frozen = {"environments": summaries, "config": copy.deepcopy(config), "operation_id": operation.id if operation else None, "operation_revision": operation.revision if operation else None, "operation_name": operation.name if operation else "临时执行", "agent_id": agent_id, "strategies": strategies, "errors": errors,
        "executor": {"agent_version": device.version, "plugin_version": device.update_state.get("plugin_version", "builtin"), "plugin_digest": device.update_state.get("plugin_digest", "builtin")}}
    row = MatrixPreview(company_id=actor.company_id, owner_id=actor.id, plan_id=plan.id if plan else None, revision=revision,
        token_hash=digest(raw), payload=frozen, expires_at=utcnow() + timedelta(minutes=5))
    db.add(row)
    if commit: db.commit()
    return {"preview_token": raw, "plan_id": plan.id if plan else None, "operation_id": operation.id if operation else None, "operation_name": operation.name if operation else "临时执行", "revision": revision, "environments": summaries, "errors": errors,
        "strategies": {s: {"name": v["name"], **v["parameters"]} for s,v in strategies.items()}, "tasks": config["tasks"], "agent_id": agent_id}


def create_run(db, actor, plan_id, payload, key, operation_id=None, commit=True, request_context=None):
    if not key or not 8 <= len(key) <= 128: fail("缺少有效 Idempotency-Key", 422)
    guard(db, actor.company_id); enabled(db, actor.company_id)
    request_hash = digest({"plan_id": plan_id, "operation_id": operation_id, "context": request_context, **payload.model_dump()})
    previous = db.scalar(select(MatrixRun).where(MatrixRun.company_id == actor.company_id, MatrixRun.owner_id == actor.id, MatrixRun.idempotency_key == key))
    if previous:
        if previous.request_hash != request_hash: fail("幂等键已用于不同请求")
        return run_view(db, previous)
    plan = owned(db, MatrixPlan, plan_id, actor, "owner_id") if plan_id else None
    operation = get_operation(db, actor, plan.config["operation_id"] if plan else operation_id) if plan or operation_id else None
    pv = db.scalar(select(MatrixPreview).where(MatrixPreview.token_hash == digest(payload.preview_token), MatrixPreview.company_id == actor.company_id, MatrixPreview.owner_id == actor.id, MatrixPreview.plan_id == plan_id))
    revision = plan.revision if plan else operation.revision if operation else 1
    if (plan and plan.deleted) or not pv or pv.expires_at < utcnow() or pv.revision != revision or payload.expected_revision != revision or pv.payload["operation_id"] != (operation.id if operation else None) or pv.payload["operation_revision"] != (operation.revision if operation else None):
        fail("执行预览已过期或配置已修改，请重新预览")
    permissions.require_tasks(db, actor, pv.payload["config"]["tasks"])
    if pv.payload["errors"]: fail("预览包含阻止项", 422)
    agent = db.get(HubAgent, pv.payload["agent_id"]); device = db.get(MatrixDevice, pv.payload["agent_id"])
    if not agent or not agent.is_active or agent.user_id != actor.id or not device: fail("设备授权已变更")
    if "listing.catalog" in pv.payload["config"]["tasks"]: enabled(db, actor.company_id, True)
    for target in pv.payload["environments"]:
        if target['site'] != 'MY': fail('当前仅支持马来西亚（MY）跨境店，请重新预览', 422)
        env = db.get(MatrixEnvironment, target["id"])
        access = db.scalar(select(MatrixAccess.id).where(MatrixAccess.agent_id == agent.id, MatrixAccess.environment_id == target["id"], MatrixAccess.available.is_(True)))
        if not env or env.revision != target["revision"] or not access or env.hub_identity != device.hub_identity: fail("环境目录已变化，请重新预览")
    run = MatrixRun(company_id=actor.company_id, owner_id=actor.id, agent_id=agent.id, plan_id=plan_id, plan_revision=revision,
        idempotency_key=key, request_hash=request_hash, frozen=copy.deepcopy(pv.payload))
    db.add(run); db.flush()
    for env in pv.payload["environments"]:
        db.add(MatrixItem(company_id=actor.company_id, run_id=run.id, environment_id=env["id"], agent_id=agent.id))
    audit(db, actor, "run.create", run.id, {"plan_revision": revision, "count": len(pv.payload["environments"])})
    if commit: db.commit()
    return run_view(db, run)


def manual_preview(db, actor, payload):
    from .schemas import PreviewInput
    guard(db, actor.company_id); enabled(db, actor.company_id)
    config = {"tasks": payload.tasks, "strategies": payload.strategies if "listing.catalog" in payload.tasks else {}}
    validate_operation(db, actor, config)
    query = environment_query(db, actor, payload.filters.model_dump())
    if not payload.all_filtered: query = query.where(MatrixEnvironment.id.in_(payload.environment_ids))
    envs = db.scalars(query.limit(1001)).all()
    if not envs or len(envs)>1000: fail("请选择1至1000个有权环境", 422)
    if not payload.all_filtered and {e.id for e in envs} != set(payload.environment_ids): fail("所选环境不再可用", 422)
    candidates = db.execute(select(MatrixAccess, HubAgent, MatrixDevice).join(HubAgent, HubAgent.id==MatrixAccess.agent_id)
        .join(MatrixDevice, MatrixDevice.agent_id==HubAgent.id).where(MatrixAccess.environment_id.in_([e.id for e in envs]),
        MatrixAccess.available.is_(True), HubAgent.company_id==actor.company_id, HubAgent.user_id==actor.id, HubAgent.is_active.is_(True))).all()
    groups = {}
    now = utcnow()
    for env in envs:
        choices = [(access, agent, device) for access, agent, device in candidates if access.environment_id==env.id and device.hub_identity==env.hub_identity]
        if not choices: fail(f"{env.name}：没有自己已授权且可访问此环境的设备，请同步环境", 422)
        site = env.override_site or env.observed_site
        def rank(choice):
            access, agent, device = choice
            ready = bool(agent.last_seen_at and agent.last_seen_at>now-timedelta(seconds=45) and device.hub_connected and not device.paused and not device.local_paused
                and access.seen_at>now-timedelta(minutes=5) and all(site in device.capabilities.get(t, []) for t in config["tasks"]))
            return (not ready, agent.id not in groups, agent.id)
        _, agent, _ = min(choices, key=rank)
        groups.setdefault(agent.id, []).append(env.id)
    batches = [preview(db, actor, None, PreviewInput(environment_ids=ids), manual_config=config, manual_agent_id=agent_id, commit=False) for agent_id, ids in groups.items()]
    db.commit()
    return {"batches": batches, "tasks": config["tasks"], "errors": [error for batch in batches for error in batch["errors"]], "environment_count": len(envs)}


def manual_runs(db, actor, payload, key):
    if not key or not 8<=len(key)<=128: fail("缺少有效 Idempotency-Key", 422)
    guard(db, actor.company_id); enabled(db, actor.company_id)
    context = digest(payload.model_dump())
    runs = [create_run(db, actor, None, pv, f"manual-{digest(key)}-{index}", commit=False, request_context=context) for index, pv in enumerate(payload.previews)]
    db.commit()
    return {"items": runs}


def run_access(db, actor, identity, manage=False):
    run = owned(db, MatrixRun, identity, actor)
    if run.owner_id != actor.id and (actor.role != Role.COMPANY_ADMIN if manage else not permissions.company_view(db, actor)):
        fail("运行不存在", 404)
    return run


def run_view(db, run, item_ids=None):
    query = select(MatrixItem).where(MatrixItem.run_id == run.id)
    if item_ids is not None: query = query.where(MatrixItem.id.in_(item_ids))
    items = db.scalars(query.order_by(MatrixItem.id)).all()
    attempts = db.scalars(select(MatrixAttempt).where(MatrixAttempt.item_id.in_([i.id for i in items])).order_by(MatrixAttempt.item_id, MatrixAttempt.number)).all()
    shops = {shop.id: shop for shop in db.scalars(select(MatrixShop).where(MatrixShop.id.in_([i.shop_id for i in items if i.shop_id])))}
    frozen_envs = {e["id"]: e for e in run.frozen.get("environments", [])}
    views = []
    for item in items:
        view = item_view(item)
        env = frozen_envs.get(item.environment_id, {})
        shop = shops.get(item.shop_id)
        view.update(environment_name=env.get("name"), container_code=env.get("container_code"),
            shop={"name": shop.name, "external_id": shop.external_id, "site": shop.site} if shop else None,
            attempts=[{"id": a.id, "number": a.number, "status": a.status, "started_at": instant(a.started_at)} for a in attempts if a.item_id == item.id])
        views.append(view)
    agent = db.get(HubAgent, run.agent_id)
    owner = db.get(User, run.owner_id)
    version = db.scalar(select(MatrixPlanVersion).where(MatrixPlanVersion.plan_id==run.plan_id,MatrixPlanVersion.revision==run.plan_revision))
    scheduled = db.scalar(select(MatrixFire.id).where(MatrixFire.run_id==run.id).limit(1)) is not None
    return {"id": run.id, "plan_id": run.plan_id, "plan_revision": run.plan_revision, "owner_id": run.owner_id, "agent_id": run.agent_id,
        "status": run.status, "stop_requested": run.stop_requested, "created_at": instant(run.created_at), "completed_at": instant(run.completed_at),
        "plan_name": version.payload.get("name") if version else None, "operation_name": run.frozen.get("operation_name"), "trigger": "scheduled" if scheduled else "manual", "device_name": agent.name if agent else None,
        "owner_name": owner.name if owner else None,
        "tasks": run.frozen["config"]["tasks"], "items": views}


def event(db, item, kind, payload, source_id=None):
    attempt_id = item.attempt_id
    if source_id and attempt_id:
        old = db.scalar(select(MatrixEvent).where(MatrixEvent.attempt_id == attempt_id, MatrixEvent.source_id == source_id))
        if old:
            if old.payload not in (payload, {**payload, "item_id": item.id}) or old.kind != kind: fail("事件幂等内容不一致")
            return old
    seq = (db.scalar(select(func.max(MatrixEvent.seq)).where(MatrixEvent.run_id == item.run_id)) or 0) + 1
    row = MatrixEvent(run_id=item.run_id, attempt_id=attempt_id, source_id=source_id or secrets.token_hex(16), seq=seq, kind=kind, payload={**payload, "item_id": item.id})
    db.add(row); db.flush()
    return row


def recompute(db, run):
    db.flush()
    states = db.scalars(select(MatrixItem.status).where(MatrixItem.run_id == run.id)).all()
    if "awaiting_attention" in states: run.status = "awaiting_attention"
    elif any(s in {"running", "queued"} for s in states): run.status = "running" if "running" in states else "queued"
    elif all(s == "succeeded" for s in states): run.status = "succeeded"
    elif all(s == "cancelled" for s in states): run.status = "cancelled"
    elif all(s == "failed" for s in states): run.status = "failed"
    else: run.status = "partial_success"
    if not any(s in ACTIVE for s in states): run.completed_at = utcnow()


def release_guard(db, item):
    env = db.get(MatrixEnvironment, item.environment_id)
    lock = hub.runtime_guard(db, item.company_id, env.container_code)
    if lock and lock.matrix_item_id == item.id:
        lock.matrix_item_id = None
        if lock.task_id == item.upload_task_id: lock.task_id = None


def sweep(db, company_id=None):
    query = select(MatrixItem.company_id, MatrixItem.id).join(MatrixAttempt, MatrixAttempt.id == MatrixItem.attempt_id).where(
        MatrixItem.status == "running", MatrixAttempt.lease_until <= utcnow())
    if company_id is not None: query = query.where(MatrixItem.company_id == company_id)
    candidates = db.execute(query.order_by(MatrixItem.company_id, MatrixItem.id)).all()
    for company_id, identity in candidates:
        guard(db, company_id)
        item = hub.lock_row(db, MatrixItem, identity)
        attempt = hub.lock_row(db, MatrixAttempt, item.attempt_id)
        if item.status != "running" or attempt.lease_until > utcnow(): continue
        item.status, item.stage, item.error = "awaiting_attention", "connection_lost", "执行器失联，请核对提交及采集状态"
        attempt.status = "awaiting_attention"
        if item.submission == "request_sent": item.submission = "unknown"
        if item.upload_task_id:
            task = db.get(HubUploadTask, item.upload_task_id)
            task.status, task.stage, task.claim_token, task.lease_expires_at = "awaiting_attention", "connection_lost", None, None
        event(db, item, "lease.expired", {"message": item.error})
        recompute(db, db.get(MatrixRun, item.run_id))
    db.commit()


def claim(db, agent, item_id):
    guard(db, agent.company_id); enabled(db, agent.company_id)
    device = db.get(MatrixDevice, agent.id)
    item = db.get(MatrixItem, item_id)
    if not item or item.company_id != agent.company_id or item.agent_id != agent.id: fail("任务不存在", 404)
    run = db.get(MatrixRun, item.run_id); env = db.get(MatrixEnvironment, item.environment_id)
    permissions.require_tasks(db, db.get(User, agent.user_id), run.frozen["config"]["tasks"])
    retransmit = item.result.get("retransmit_only", False)
    if run.owner_id != agent.user_id or not device or device.paused or device.local_paused or not retransmit and not device.hub_connected: fail("设备当前不可领取")
    if item.status != "queued" or run.stop_requested: fail("任务已领取或已取消")
    if not agent.last_seen_at or agent.last_seen_at < utcnow() - timedelta(seconds=45): fail("设备已离线")
    if not retransmit and env.hub_identity != device.hub_identity: fail("Hub身份已变更")
    target = next(e for e in run.frozen["environments"] if e["id"] == env.id)
    if not retransmit and target['site'] != 'MY': fail('当前仅支持马来西亚（MY）跨境店', 422)
    expected_executor = run.frozen.get("executor")
    actual_executor = {"agent_version": device.version, "plugin_version": device.update_state.get("plugin_version", "builtin"), "plugin_digest": device.update_state.get("plugin_digest", "builtin")}
    if not retransmit and expected_executor and expected_executor != actual_executor: reject_queued(db, item, "执行器或插件版本已变化，请重新预览创建运行")
    if not retransmit and env.revision != target["revision"]: reject_queued(db, item, "环境已变化，请重新创建运行")
    access = db.scalar(select(MatrixAccess).where(MatrixAccess.agent_id == agent.id, MatrixAccess.environment_id == env.id, MatrixAccess.available.is_(True)))
    if not retransmit and (not access or access.seen_at < utcnow() - timedelta(minutes=5)): fail("目录已过期，请先完整同步")
    for task in run.frozen["config"]["tasks"]:
        if not retransmit and target["site"] not in device.capabilities.get(task, []): fail("插件能力已变化")
    if not retransmit and "listing.catalog" in run.frozen["config"]["tasks"]: enabled(db, agent.company_id, True)
    if db.scalar(select(MatrixItem.id).where(MatrixItem.agent_id == agent.id, MatrixItem.status == "running")) or db.scalar(select(HubUploadTask.id).where(HubUploadTask.agent_id == agent.id, HubUploadTask.status == "running")):
        fail("设备正在执行其他任务")
    lock = hub.runtime_guard(db, agent.company_id, env.container_code, create=True)
    if lock.task_id or lock.matrix_item_id: fail("环境已被其他任务占用")
    raw = secrets.token_urlsafe(32)
    lock.fencing += 1
    attempt = MatrixAttempt(item_id=item.id, agent_id=agent.id, number=(db.scalar(select(func.max(MatrixAttempt.number)).where(MatrixAttempt.item_id == item.id)) or 0)+1,
        token_hash=digest(raw), fencing=lock.fencing, lease_until=utcnow()+timedelta(seconds=90))
    db.add(attempt); db.flush()
    item.attempt_id, item.status, item.stage = attempt.id, "running", "prechecking"
    lock.matrix_item_id = item.id
    run.status = "running"
    event(db, item, "claimed", {"stage": item.stage, **actual_executor})
    db.commit()
    return {"item": item_view(item), "attempt_id": attempt.id, "claim_token": raw, "fencing": attempt.fencing, "environment": target,
        "tasks": run.frozen["config"]["tasks"], "lease_seconds": 90}


def reject_queued(db, item, message):
    item.status, item.stage, item.error = "failed", "precheck_failed", message
    event(db, item, "precheck.failed", {"message": message})
    recompute(db, db.get(MatrixRun, item.run_id))
    db.commit()
    fail(message)


def checked_attempt(db, agent, item_id, payload, allow_attention=False):
    guard(db, agent.company_id)
    item = db.get(MatrixItem, item_id)
    if not item or item.company_id != agent.company_id or item.agent_id != agent.id: fail("任务不存在", 404)
    attempt = db.get(MatrixAttempt, item.attempt_id) if item.attempt_id else None
    run = db.get(MatrixRun, item.run_id)
    env = db.get(MatrixEnvironment, item.environment_id)
    device = db.get(MatrixDevice, agent.id)
    lock = hub.runtime_guard(db, agent.company_id, env.container_code)
    if not attempt or not hmac.compare_digest(attempt.token_hash, digest(payload.claim_token)) or attempt.fencing != payload.fencing or attempt.agent_id != agent.id:
        fail("领取凭证已失效")
    if not lock or lock.matrix_item_id != item.id or lock.fencing != attempt.fencing or attempt.status != "running" or attempt.lease_until <= utcnow() or item.status != "running":
        fail("租约已失效，请核对平台")
    if run.owner_id != agent.user_id or not device or not item.result.get("retransmit_only") and device.hub_identity != env.hub_identity: fail("设备身份已变化")
    if not item.result.get("retransmit_only") and not db.scalar(select(MatrixAccess.id).where(MatrixAccess.agent_id == agent.id, MatrixAccess.environment_id == env.id, MatrixAccess.available.is_(True))):
        fail("环境访问权限已撤销，禁止继续执行")
    return item, attempt, run


def bind_environment_target(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    permissions.require_tasks(db, db.get(User, agent.user_id), run.frozen["config"]["tasks"])
    env = db.get(MatrixEnvironment, item.environment_id)
    target = next(e for e in run.frozen["environments"] if e["id"] == env.id)
    if target["site"] != "MY": fail("当前仅支持马来西亚（MY）跨境店", 422)
    shop = db.scalar(select(MatrixShop).where(MatrixShop.company_id==agent.company_id, MatrixShop.environment_id==env.id))
    if not shop:
        shop = MatrixShop(company_id=agent.company_id, environment_id=env.id, external_id=None, site=target["site"], name=env.name)
        db.add(shop); db.flush()
    shop.name, shop.site = env.name, target["site"]
    env.shop_id, item.shop_id = shop.id, shop.id
    identity = {"site": target["site"], "environment_id": env.id, "name": env.name}
    event(db, item, "environment.bound", {"environment_id": env.id, "message": "采集和上品结果按所选环境归档"})
    db.commit()
    return {"shop_id": shop.id, "identity": identity}


def bind_identity(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    env = db.get(MatrixEnvironment, item.environment_id)
    site = next(e["site"] for e in run.frozen["environments"] if e["id"] == env.id)
    identity = payload.identity
    if identity.site != site: fail("平台站点与方案不一致")
    shop = db.scalar(select(MatrixShop).where(MatrixShop.company_id == agent.company_id, MatrixShop.site == site, MatrixShop.external_id == identity.external_id))
    if not shop:
        shop = MatrixShop(company_id=agent.company_id, site=site, external_id=identity.external_id, name=identity.name)
        db.add(shop); db.flush()
    if env.shop_id and env.shop_id != shop.id: fail("店铺身份与历史绑定冲突，请人工核对")
    env.shop_id, env.observed_site, item.shop_id, shop.name = shop.id, site, shop.id, identity.name
    event(db, item, "identity.confirmed", {"shop_id": shop.id, "site": site})
    db.commit()
    return {"shop_id": shop.id}


def report(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    requested = payload.status
    tasks = run.frozen["config"]["tasks"]
    if item.submission in {"request_sent", "unknown"}: requested = "awaiting_attention"
    if requested == "succeeded":
        if "listing.catalog" in tasks and item.submission != "confirmed": fail("上品缺少持久化确认")
        if "listing.catalog" in tasks and item.result.get("listing", {}).get("rejected"): fail("部分商品被拒绝，不能报告全成功")
        if "shop.collect" in tasks and item.collection_status != "committed": fail("采集数据尚未提交")
        if "shop.collect" in tasks:
            from .models import MatrixCollection
            snap = db.scalar(select(MatrixCollection).where(MatrixCollection.item_id == item.id, MatrixCollection.status == "committed").order_by(MatrixCollection.id.desc()))
            if snap and snap.quality.get("optional_errors"): requested = "partial_success"
    if requested == "partial_success" and not (item.submission == "confirmed" or item.collection_status == "committed"): requested = "failed"
    item.status, item.error = requested, payload.message or None
    if requested == "awaiting_attention" and item.submission == "request_sent": item.submission = "unknown"
    item.stage = requested
    attempt.status = requested
    if item.upload_task_id:
        task = db.get(HubUploadTask, item.upload_task_id)
        if task.status == "running":
            task.status = "awaiting_attention" if requested == "awaiting_attention" else "failed"
            task.stage, task.failure_reason = item.stage, item.error
            task.claim_token, task.lease_expires_at = None, None
            hub.finish_attempt(db, task, task.status)
    if requested != "awaiting_attention": release_guard(db, item)
    if item.submission == "not_started" and requested in {"failed", "cancelled"}:
        for row in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id == item.id, MatrixAllocation.state.in_(["reserved", "prepared"]))): row.state = "released"
    event(db, item, "item.result", {"status": requested, "message": payload.message})
    recompute(db, run); db.commit()
    return item_view(item)
