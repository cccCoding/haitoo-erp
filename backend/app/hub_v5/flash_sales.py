"""秒杀续期台账；只有用户明确选择的到期活动可进入写操作。"""
from datetime import timedelta, timezone
from sqlalchemy import select, func, or_, update
from .models import MatrixFlashActivity as Activity, MatrixFlashRenewal as Renewal, MatrixFlashSnapshot as Snapshot, MatrixItem, MatrixRun, MatrixEnvironment
from ..models import User
from . import service as s, permissions

TASK = "promotion.flash_sale.renew"
COLLECT_TASK = "promotion.flash_sale.collect"
TERMINAL = {"published", "failed", "skipped", "cancelled"}
TRANSITIONS = {
    "pending": {"terminate_intent", "copy_intent", "skipped", "failed"},
    "terminate_intent": {"terminated", "unknown"},
    "terminated": {"copy_intent", "unknown"},
    "copy_intent": {"draft_confirmed", "unknown"},
    "draft_confirmed": {"publish_intent", "unknown"},
    "publish_intent": {"published", "unknown"},
}


def utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value else None


def view(db, row):
    activity = db.get(Activity, row.activity_id)
    return {"id": row.id, "activity_id": row.activity_id, "external_id": activity.external_id,
        "name": activity.name, "environment_id": activity.environment_id, "original_ends_at":s.instant(activity.ends_at), "stage": row.stage,
        "new_activity_id": row.new_activity_id, "starts_at": s.instant(row.starts_at), "ends_at": s.instant(row.ends_at),
        "terminated": row.terminated, "evidence": row.evidence, "error": row.error, "item_id": row.item_id}


def rows(db, item_id):
    return list(db.scalars(select(Renewal).where(Renewal.item_id==item_id).order_by(Renewal.id)))


def has_unresolved(db, item_id):
    return any(r.stage not in TERMINAL for r in rows(db, item_id))


def has_failures(db, item_id):
    return any(r.stage in {"failed", "cancelled"} for r in rows(db, item_id))


def checked(db, agent, item_id, payload, writing=False):
    item, attempt, run = s.checked_attempt(db, agent, item_id, payload)
    if not {TASK,COLLECT_TASK}&set(run.frozen["config"]["tasks"]): s.fail("运行未包含秒杀活动任务", 403)
    s.enabled(db, agent.company_id)
    permissions.require_tasks(db, db.get(User, run.owner_id), [TASK])
    if writing and run.stop_requested: s.fail("运行已请求停止，禁止开始新的平台写操作")
    return item, attempt, run


def eligible(activity, config, now):
    selected = config.get("selected_flash_ids")
    if selected is not None:
        return activity.id in selected and activity.status=="expired" and activity.ends_at <= now
    return activity.status=="ongoing" and now < activity.ends_at <= now+timedelta(hours=config.get("flash_sale", {}).get("threshold_hours",12))


def scan(db, agent, item_id, payload):
    item, attempt, run = checked(db, agent, item_id, payload, writing=True)
    now = s.utcnow()
    records = []
    read_only=TASK not in run.frozen["config"]["tasks"]
    db.execute(update(Activity).where(Activity.company_id==agent.company_id,Activity.environment_id==item.environment_id).values(present=False))
    for observed in payload.activities:
        activity = db.scalar(select(Activity).where(Activity.company_id==agent.company_id,
            Activity.environment_id==item.environment_id, Activity.external_id==observed.external_id))
        if not activity:
            activity = Activity(company_id=agent.company_id, environment_id=item.environment_id, external_id=observed.external_id,
                dismissed_by=[])
            db.add(activity)
        activity.present=True
        if observed.starts_at is not None:activity.starts_at=utc(observed.starts_at)
        activity.name, activity.status, activity.ends_at = observed.name, observed.status, utc(observed.ends_at)
        activity.product_count, activity.observed_at, activity.source_item_id = observed.product_count, now, item.id
        db.flush()
        renewal = db.scalar(select(Renewal).where(Renewal.activity_id==activity.id))
        if not read_only and eligible(activity, run.frozen["config"], now):
            if not renewal:
                renewal = Renewal(company_id=agent.company_id, activity_id=activity.id, item_id=item.id, stage="pending")
                db.add(renewal); db.flush()
            if renewal.stage in {"failed","skipped"} and not renewal.terminated:
                renewal.item_id,renewal.stage,renewal.error=item.id,"pending",None
            if renewal.item_id==item.id: records.append(renewal)
    # 重试不能丢掉旧记录；失联前的意图仍需只读核对。
    for renewal in rows(db,item.id):
        if renewal not in records: records.append(renewal)
    snapshot=db.scalar(select(Snapshot).where(Snapshot.company_id==agent.company_id,Snapshot.environment_id==item.environment_id))
    if not snapshot:
        snapshot=Snapshot(company_id=agent.company_id,environment_id=item.environment_id)
        db.add(snapshot)
    snapshot.observed_at,snapshot.source_item_id,snapshot.activity_count=now,item.id,len(payload.activities)
    ids = [r.id for r in records]
    skipped=[]
    selected=run.frozen["config"].get("selected_flash_ids")
    if selected is not None:
        observed={a.external_id for a in payload.activities}
        own={r.activity_id for r in records}
        for activity in db.scalars(select(Activity).where(Activity.company_id==agent.company_id,
                Activity.environment_id==item.environment_id,Activity.id.in_(selected))):
            if activity.id not in own:
                reason="活动已处理、状态变化或已有续期过程，未重复创建"
                if activity.external_id not in observed:
                    activity.status="unknown"
                    reason="完整活动列表未找到所选活动，未执行续期"
                skipped.append({"activity_id":activity.id,"external_id":activity.external_id,"reason":reason})
                s.event(db,item,"flash.skipped",{"stage":"flash_skipped","message":f"{activity.name}：{reason}"})
    item.result = {**item.result, "flash_sale": {"scan_complete":True, "complete":False, "renewal_ids":ids,
        "observed_at":now.isoformat()+"Z","selection_skipped":skipped}}
    s.event(db,item,"flash.scan",{"stage":"flash_scan","message":f"完整扫描商家秒杀活动 {len(payload.activities)} 个，处理 {len(records)} 个"})
    db.commit()
    return {"renewals":[view(db,r) for r in records]}


def step(db, agent, item_id, renewal_id, payload):
    intent = payload.stage.endswith("_intent")
    item, attempt, run = checked(db, agent, item_id, payload, writing=intent)
    if TASK not in run.frozen["config"]["tasks"]:s.fail("只读同步任务不能操作续期台账",403)
    row = s.owned(db,Renewal,renewal_id,agent)
    if row.item_id!=item.id: s.fail("活动不属于当前执行项",404)
    activity = db.get(Activity,row.activity_id)
    # 相同状态仅允许完全相同的重传。
    if row.stage==payload.stage:
        if (payload.new_activity_id and payload.new_activity_id!=row.new_activity_id
                or payload.starts_at and utc(payload.starts_at)!=row.starts_at
                or payload.ends_at and utc(payload.ends_at)!=row.ends_at): s.fail("重复回执内容不一致")
        if payload.error:
            row.error,row.updated_at=payload.error,s.utcnow()
            s.event(db,item,"flash.error",{"stage":"flash_attention","renewal_id":row.id,"message":payload.error})
            db.commit()
        return view(db,row)
    if payload.stage not in TRANSITIONS.get(row.stage,set()): s.fail("续期阶段不允许此转换")
    if row.stage=="pending" and intent:
        if not eligible(activity,run.frozen["config"],s.utcnow()): s.fail("活动状态已变化，不能开始续期")
        if payload.stage=="terminate_intent" and activity.status!="ongoing": s.fail("到期活动不能终止")
        if payload.stage=="copy_intent" and activity.status!="expired": s.fail("进行中活动必须先终止")
    if payload.stage in {"draft_confirmed","publish_intent","published"}:
        new_id = payload.new_activity_id or row.new_activity_id
        if not new_id or new_id==activity.external_id: s.fail("缺少可核对的新活动ID")
        conflict = db.scalar(select(Renewal.id).where(Renewal.company_id==row.company_id, Renewal.id!=row.id,
            Renewal.new_activity_id==new_id, Renewal.activity_id.in_(select(Activity.id).where(Activity.environment_id==activity.environment_id))))
        if conflict: s.fail("新活动已关联其他续期过程")
        row.new_activity_id = new_id
    if payload.stage=="publish_intent":
        start,end=utc(payload.starts_at),utc(payload.ends_at)
        if not start or not end or start<=s.utcnow() or end-start!=timedelta(hours=72): s.fail("新活动必须从未来有效时间开始并持续72小时",422)
        row.starts_at,row.ends_at=start,end
    if payload.stage=="published":
        if not payload.evidence or utc(payload.starts_at)!=row.starts_at or utc(payload.ends_at)!=row.ends_at:
            s.fail("发布回执缺少明确凭据或时间不匹配",422)
    row.stage,row.evidence,row.error,row.updated_at=payload.stage,payload.evidence,payload.error,s.utcnow()
    if row.stage=="terminated": row.terminated=True
    s.event(db,item,"flash.step",{"stage":"flash_"+row.stage,"renewal_id":row.id,"message":payload.error or f"{activity.name}：{row.stage}"})
    db.commit()
    return view(db,row)


def complete(db,agent,item_id,payload):
    item,attempt,run=checked(db,agent,item_id,payload)
    summary=item.result.get("flash_sale",{})
    if not summary.get("scan_complete"):s.fail("尚未完成完整活动扫描")
    values=rows(db,item_id)
    summary={**summary,"complete":not has_unresolved(db,item_id),"succeeded":sum(r.stage=="published" for r in values),
        "failed":sum(r.stage in {"failed","cancelled"} for r in values),"awaiting_attention":sum(r.stage not in TERMINAL for r in values),
        "skipped":sum(r.stage=="skipped" for r in values)+len(summary.get("selection_skipped",[]))}
    item.result={**item.result,"flash_sale":summary}
    db.commit()
    return summary


def activity_query(db,actor):
    return select(Activity).where(Activity.company_id==actor.company_id,
        Activity.environment_id.in_(s.accessible_ids(db,actor)))


def candidate_query(db,actor,start=None,end=None,apply_dates=True):
    now=s.utcnow()
    start,end=utc(start) if start else now-timedelta(hours=72),utc(end) if end else now
    if apply_dates and (end<start or end-start>timedelta(days=366)):s.fail("请选择不超过366天的有效日期范围",422)
    available=select(Renewal.activity_id).where(or_(Renewal.stage.not_in(["failed","skipped"]),Renewal.terminated.is_(True)))
    busy_runs=select(MatrixItem.run_id).where(MatrixItem.company_id==actor.company_id,MatrixItem.status.in_(["queued","running"]))
    busy_batches=select(MatrixRun.frozen["batch_key"].as_string()).where(MatrixRun.company_id==actor.company_id,
        MatrixRun.id.in_(busy_runs),MatrixRun.frozen["batch_key"].as_string().is_not(None))
    return activity_query(db,actor).join(MatrixItem,MatrixItem.id==Activity.source_item_id).join(MatrixRun,MatrixRun.id==MatrixItem.run_id).where(
        Activity.present.is_(True),Activity.status=="expired",Activity.ends_at<=now,
        *([Activity.ends_at>=start,Activity.ends_at<=min(end,now)] if apply_dates else []),
        Activity.id.not_in(available),MatrixItem.run_id.not_in(busy_runs),
        or_(MatrixRun.frozen["batch_key"].as_string().is_(None),MatrixRun.frozen["batch_key"].as_string().not_in(busy_batches)))


def activity_view(db,a,can_renew=False,renewal=None):
    env=db.get(MatrixEnvironment,a.environment_id)
    return {"id":a.id,"environment_id":a.environment_id,"environment_name":env.name,"container_code":env.container_code,
        "name":a.name,"external_id":a.external_id,"status":a.status,"starts_at":s.instant(a.starts_at),
        "ends_at":s.instant(a.ends_at),"observed_at":s.instant(a.observed_at),"product_count":a.product_count,
        "can_renew":can_renew,"renewal":view(db,renewal) if renewal else None}


def candidates(db,actor,start=None,end=None,page=1,page_size=50):
    query=candidate_query(db,actor,start,end)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    records=list(db.scalars(query.order_by(Activity.ends_at.desc(),Activity.id.desc()).offset((page-1)*page_size).limit(page_size)))
    unread=[a for a in db.scalars(query) if actor.id not in a.dismissed_by]
    return {"items":[{**activity_view(db,a,True),"dismissed":actor.id in a.dismissed_by} for a in records],"total":total,
        "unread":len(unread),"environment_count":len({a.environment_id for a in unread})}


def environment_access(db,actor,identity):
    env=db.scalar(s.environment_query(db,actor).where(MatrixEnvironment.id==identity))
    if env is None:s.fail("环境不可访问",404)
    return env


def environment_activities(db,actor,identity,status="",start=None,end=None,page=1,page_size=50):
    env=environment_access(db,actor,identity)
    base=activity_query(db,actor).where(Activity.environment_id==identity,Activity.present.is_(True))
    snapshot=db.scalar(select(Snapshot).where(Snapshot.company_id==actor.company_id,Snapshot.environment_id==identity))
    counts=dict(db.execute(base.with_only_columns(Activity.status,func.count()).group_by(Activity.status)).all()) if snapshot else None
    query=base
    if status:query=query.where(Activity.status==status)
    if status=="expired" and start is None and end is None:
        query=query.where(Activity.ends_at>=s.utcnow()-timedelta(hours=72),Activity.ends_at<=s.utcnow())
    elif start is not None or end is not None:
        left,right=utc(start) if start else None,utc(end) if end else None
        if left and right and (right<left or right-left>timedelta(days=366)):s.fail("请选择不超过366天的有效日期范围",422)
        if left:query=query.where(Activity.ends_at>=left)
        if right:query=query.where(Activity.ends_at<=right)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    values=list(db.scalars(query.order_by(Activity.ends_at.desc(),Activity.id.desc()).offset((page-1)*page_size).limit(page_size)))
    allowed=set(db.scalars(candidate_query(db,actor,apply_dates=False).where(Activity.id.in_([a.id for a in values])).with_only_columns(Activity.id)))
    renewals={r.activity_id:r for r in db.scalars(select(Renewal).where(Renewal.activity_id.in_([a.id for a in values])))}
    active=db.scalar(select(MatrixItem).join(MatrixRun,MatrixRun.id==MatrixItem.run_id).where(MatrixItem.company_id==actor.company_id,
        MatrixItem.environment_id==identity,MatrixRun.owner_id==actor.id,MatrixItem.status.in_(["queued","running"])).order_by(MatrixItem.id.desc()).limit(1))
    return {"environment":{"id":env.id,"name":env.name,"container_code":env.container_code,"site":env.override_site or env.observed_site},
        "snapshot":{"observed_at":s.instant(snapshot.observed_at),"count":snapshot.activity_count,"timezone":"Asia/Kuala_Lumpur"} if snapshot else None,
        "counts":{state:counts.get(state,0) for state in ("ongoing","scheduled","expired","terminated","unknown")} if counts is not None else None,
        "total":total,"items":[activity_view(db,a,a.id in allowed,renewals.get(a.id)) for a in values],
        "active_sync":{"run_id":active.run_id,"status":active.status,"stage":active.stage} if active and COLLECT_TASK in db.get(MatrixRun,active.run_id).frozen["config"]["tasks"] else None}


def sync_environment(db,actor,identity,key):
    from .schemas import ManualPreviewInput, RunInput
    from ..supply_common import digest
    if not key or not 8<=len(key)<=128:s.fail("缺少有效 Idempotency-Key",422)
    s.guard(db,actor.company_id);s.enabled(db,actor.company_id)
    environment_access(db,actor,identity)
    run_key="flash-sync-"+digest(key)
    previous=db.scalar(select(MatrixRun).where(MatrixRun.company_id==actor.company_id,MatrixRun.owner_id==actor.id,MatrixRun.idempotency_key==run_key))
    if previous:
        if previous.frozen['config']['tasks']!=[COLLECT_TASK] or [e['id'] for e in previous.frozen['environments']]!=[identity]:s.fail("幂等键已用于其他请求")
        return s.run_view(db,previous)
    # 多次点击不同幂等键也复用同环境未结束的只读同步。
    for active in db.scalars(select(MatrixRun).join(MatrixItem,MatrixItem.run_id==MatrixRun.id).where(MatrixRun.company_id==actor.company_id,
            MatrixRun.owner_id==actor.id,MatrixItem.environment_id==identity,MatrixItem.status.in_(["queued","running"]))):
        if active.frozen['config']['tasks']==[COLLECT_TASK]:return s.run_view(db,active)
    preview=s.manual_preview(db,actor,ManualPreviewInput(tasks=[COLLECT_TASK],environment_ids=[identity]))
    if preview['errors']:s.fail("；".join(preview['errors']),422)
    batch=preview['batches'][0]
    return s.create_run(db,actor,None,RunInput(preview_token=batch['preview_token'],expected_revision=batch['revision']),run_key)


def selection_preview(db,actor,payload):
    from .schemas import ManualPreviewInput
    s.guard(db,actor.company_id)
    activities=list(db.scalars(activity_query(db,actor).where(Activity.id.in_(payload.activity_ids))))
    if len(activities)!=len(payload.activity_ids) or any(not a.present or a.status!="expired" or a.ends_at>s.utcnow() for a in activities):
        s.fail("到期活动已变化或不可访问，请刷新后重选")
    allowed=set(db.scalars(candidate_query(db,actor,apply_dates=False).where(Activity.id.in_(payload.activity_ids)).with_only_columns(Activity.id)))
    if allowed!=set(payload.activity_ids):s.fail("活动已处理、正在扫描或不可续期，请刷新后重新选择")
    for a in activities:
        existing=db.scalar(select(Renewal).where(Renewal.activity_id==a.id))
        if existing and existing.stage not in {"failed","skipped"}:s.fail("所选活动已处理或有未解决的续期过程")
    pv=s.manual_preview(db,actor,ManualPreviewInput(tasks=[TASK],environment_ids=list({a.environment_id for a in activities})),selected_flash_ids=payload.activity_ids)
    return pv


def dismiss(db,actor,payload):
    s.guard(db,actor.company_id)
    records=list(db.scalars(activity_query(db,actor).where(Activity.id.in_(payload.activity_ids))))
    if len(records)!=len(payload.activity_ids):s.fail("活动不存在",404)
    for a in records:a.dismissed_by=sorted(set(a.dismissed_by)|{actor.id})
    db.commit()
    return {"dismissed":len(records)}


def resolve(db,actor,identity,payload):
    s.guard(db,actor.company_id)
    row=s.owned(db,Renewal,identity,actor)
    item=s.owned(db,MatrixItem,row.item_id,actor)
    run=s.run_access(db,actor,item.run_id,manage=True)
    if row.stage=="published" or item.status in {"queued","running"}:s.fail("当前状态不能人工处理")
    if not db.scalar(activity_query(db,actor).where(Activity.id==row.activity_id)):s.fail("环境已不可访问",403)
    if payload.action=="confirm-published":
        if not payload.new_activity_id or payload.new_activity_id==db.get(Activity,row.activity_id).external_id:s.fail("请填写新活动ID",422)
        start,end=utc(payload.starts_at),utc(payload.ends_at)
        if not start or not end or end-start!=timedelta(hours=72):s.fail("请填写核对的新活动起止时间，时长须为72小时",422)
        activity=db.get(Activity,row.activity_id)
        conflict=db.scalar(select(Renewal.id).where(Renewal.company_id==actor.company_id,Renewal.id!=row.id,
            Renewal.new_activity_id==payload.new_activity_id,Renewal.activity_id.in_(select(Activity.id).where(Activity.environment_id==activity.environment_id))))
        if conflict:s.fail("新活动已经关联其他续期过程")
        row.new_activity_id,row.starts_at,row.ends_at,row.stage=payload.new_activity_id,start,end,"published"
    elif payload.action=="resume":
        if actor.id!=run.owner_id or run.stop_requested:s.fail("仅所有者可恢复未停止的运行",403)
        permissions.require_tasks(db,actor,[TASK]);s.enabled(db,actor.company_id)
        if payload.verified_stage is None:s.fail("请明确核对平台当前阶段",422)
        if row.terminated and payload.verified_stage=="pending":s.fail("旧活动已终止，不能恢复为终止前")
        if payload.verified_stage=="draft_confirmed":
            if not payload.new_activity_id:s.fail("请填写核对后的草稿ID",422)
            row.new_activity_id=payload.new_activity_id
        else:row.new_activity_id=None
        row.stage=payload.verified_stage
        if row.stage=="terminated":row.terminated=True
        waiting=any(other.id!=row.id and other.stage in {"terminate_intent","copy_intent","publish_intent","unknown"} for other in rows(db,item.id))
        item.status,item.stage,item.error=("awaiting_attention","awaiting_attention","请继续核对同环境其他结果未知的活动") if waiting else ("queued","queued",None)
    else:
        if row.stage in {"terminate_intent","copy_intent","publish_intent","unknown"}:s.fail("操作结果未知，请先核对平台状态再恢复或确认发布")
        row.stage="cancelled"
    row.evidence,row.error,row.updated_at=payload.evidence,None,s.utcnow()
    if payload.action!="resume":
        if not has_unresolved(db,item.id):
            values=rows(db,item.id)
            summary=item.result.get("flash_sale",{})
            item.result={**item.result,"flash_sale":{**item.result.get("flash_sale",{}),"complete":True,
                "succeeded":sum(r.stage=="published" for r in values),"failed":sum(r.stage in {"failed","cancelled"} for r in values),
                "awaiting_attention":0,"skipped":sum(r.stage=="skipped" for r in values)+len(summary.get("selection_skipped",[]))}}
            item.status="partial_success" if has_failures(db,item.id) or any(t!="promotion.flash_sale.renew" for t in run.frozen["config"]["tasks"]) else "succeeded"
    if not has_unresolved(db,item.id) or payload.action=="resume" and item.status=="queued":s.release_guard(db,item)
    s.audit(db,actor,"flash."+payload.action,row.id,payload.model_dump(mode="json"))
    s.event(db,item,"manual.resolve",{"stage":"flash_resolved","message":payload.evidence,"renewal_id":row.id})
    s.recompute(db,run);db.commit()
    return view(db,row)


def recheck(db,agent,item_id,renewal_id,payload):
    item,attempt,run=checked(db,agent,item_id,payload)
    row=s.owned(db,Renewal,renewal_id,agent)
    if row.item_id!=item.id:s.fail("活动不属于当前执行项",404)
    activity=db.get(Activity,row.activity_id)
    if payload.activity.external_id!=activity.external_id:s.fail("复核活动ID不一致")
    activity.status,activity.ends_at,activity.observed_at=payload.activity.status,utc(payload.activity.ends_at),s.utcnow()
    activity.source_item_id=item.id
    allowed=eligible(activity,run.frozen["config"],s.utcnow())
    db.commit()
    return {"eligible":allowed,"status":activity.status}
