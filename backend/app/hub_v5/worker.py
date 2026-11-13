"""矩阵云调度：唯一触发、离线错过和货盘FIFO衔接。"""
import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from ..database import SessionLocal
from ..schema_version import assert_schema_current
from ..models import User, HubAgent, Company
from ..logging_config import configure_logging
from .models import MatrixPlan, MatrixFire, MatrixRun, MatrixDevice, MatrixItem, MatrixCompany, MatrixEnvironment
from .schemas import Input, RunInput
from . import service as s, permissions
from .listing import enqueue

logger=logging.getLogger(__name__)


def schedule_plan(db, identity, now=None):
    now=now or datetime.now(timezone.utc)
    plan=db.get(MatrixPlan,identity)
    if not plan or plan.deleted or not plan.config.get("scheduled"):return
    company_id=plan.company_id
    db.rollback()
    s.guard(db,company_id)
    from ..hub import lock_row
    plan=lock_row(db,MatrixPlan,identity)
    conf=db.get(MatrixCompany,plan.company_id)
    owner=db.get(User,plan.owner_id)
    agent=db.get(HubAgent,plan.agent_id)
    if not conf or not conf.enabled or not owner or not owner.is_active or not agent or not agent.is_active or agent.user_id!=owner.id:return
    operation=s.get_operation(db,owner,plan.config["operation_id"])
    if not permissions.tasks_allowed(db,owner,operation.config["tasks"]):return
    tz=ZoneInfo("Asia/Shanghai")
    local=now.astimezone(tz)
    interval=plan.config.get("schedule_mode")=="interval"
    if interval:
        if operation.config["tasks"] != ["promotion.flash_sale.renew"]:return
        hours=plan.config.get("interval_hours",2)
        if hours not in (2,4,6):return
        fires=[local.replace(hour=(local.hour//hours)*hours,minute=0,second=0,microsecond=0)]
    else:
        hour,minute=map(int,plan.config["time"].split(":"))
        fires=[(local+timedelta(days=offset)).replace(hour=hour,minute=minute,second=0,microsecond=0) for offset in (-1,0)]
    for fire_local in fires:
        fire=fire_local.astimezone(timezone.utc).replace(tzinfo=None)
        if fire < plan.updated_at:continue
        if fire>now.replace(tzinfo=None):continue
        existing=db.scalar(select(MatrixFire).where(MatrixFire.plan_id==plan.id,MatrixFire.fire_at==fire).order_by(MatrixFire.id.desc()).limit(1))
        if existing:
            if existing.status=="preparing" and now.replace(tzinfo=None)-fire>timedelta(minutes=2):
                created=db.scalar(select(MatrixRun).where(MatrixRun.company_id==plan.company_id,MatrixRun.owner_id==plan.owner_id,MatrixRun.idempotency_key==f"schedule-{existing.id}"))
                existing.status="created" if created else "missed"
                existing.run_id=created.id if created else None
                db.commit()
            continue
        age=now.replace(tzinfo=None)-fire
        busy=db.scalar(select(MatrixRun.id).where(MatrixRun.plan_id==plan.id,MatrixRun.status.in_(s.ACTIVE)))
        online=agent.last_seen_at and agent.last_seen_at>s.utcnow()-timedelta(seconds=45)
        device=db.get(MatrixDevice,agent.id)
        state="skipped_busy" if busy else "missed" if age>timedelta(seconds=60) or not online or not device or device.paused or device.local_paused else "preparing"
        row=MatrixFire(plan_id=plan.id,revision=plan.revision,fire_at=fire,status=state)
        db.add(row);db.commit()
        if state!="preparing":continue
        # create_run 内再次校验方案、访问关系和参数，触发记录不等于执行授权。
        try:
            db.refresh(plan)
            if plan.deleted or not plan.config.get("scheduled") or plan.revision!=row.revision:
                row.status="cancelled_changed";db.commit();continue
            pv=s.preview(db,owner,plan.id,Input())
            if pv["revision"]!=row.revision:
                row=db.get(MatrixFire,row.id);row.status="cancelled_changed";db.commit();continue
            run=s.create_run(db,owner,plan.id,RunInput(preview_token=pv["preview_token"],expected_revision=pv["revision"]),f"schedule-{row.id}")
            row=db.get(MatrixFire,row.id);row.status,row.run_id="created",run["id"];db.commit()
        except Exception:
            db.rollback();row=db.get(MatrixFire,row.id);row.status="failed";db.commit()
            logger.warning("定时方案预检失败 plan=%s fire=%s",identity,row.id)


def cycle(factory=SessionLocal):
    with factory() as db:
        s.sweep(db)
        plan_ids=list(db.scalars(select(MatrixPlan.id).where(MatrixPlan.deleted.is_(False))))
        items=list(db.scalars(select(MatrixItem.id).where(MatrixItem.status=="running",MatrixItem.stage=="waiting_supply").order_by(MatrixItem.id)))
    for identity in plan_ids:
        with factory() as db:
            try:schedule_plan(db,identity)
            except Exception:db.rollback();logger.exception("矩阵调度失败 plan=%s",identity)
    for identity in items:
        with factory() as db:
            try:
                item=db.get(MatrixItem,identity);s.guard(db,item.company_id);db.refresh(item)
                run=db.get(MatrixRun,item.run_id)
                if item.status=="running" and not run.stop_requested and permissions.tasks_allowed(db,db.get(User,run.owner_id),run.frozen["config"]["tasks"]):enqueue(db,item,run)
                db.commit()
            except Exception:db.rollback();logger.warning("货盘准备失败 item=%s",identity)


def main():
    from ..database import engine
    configure_logging();assert_schema_current(engine)
    while True:
        cycle();time.sleep(5)


if __name__=="__main__":main()
