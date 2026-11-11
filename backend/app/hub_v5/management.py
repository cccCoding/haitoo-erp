"""公司管理员的成员授权、全公司设备与执行统计。"""
from collections import Counter, defaultdict
from typing import Literal
from datetime import date, datetime, time, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from ..database import get_db
from ..models import User, Role, HubAgent
from .api import matrix_admin
from .models import MatrixMemberPermission, MatrixRun, MatrixItem, MatrixCommand, MatrixAccess, MatrixEnvironment, MatrixShop
from .schemas import MemberPermissionInput
from . import service as s, permissions

router = APIRouter(prefix="/hub-v5/admin", tags=["矩阵管理"])


def member_view(db, user):
    return {"id": user.id, "name": user.name, "user_code": user.user_code, "role": user.role.value,
        "is_active": user.is_active, "is_expired": user.role == Role.SUPPLY_USER and permissions.supply_user_is_expired(user), **permissions.access(db, user)}


@router.get("/members")
def members(q: str = Query("",max_length=200), actor=Depends(matrix_admin), db=Depends(get_db)):
    query=select(User).where(User.company_id==actor.company_id,User.role.in_(permissions.ROLES))
    if q:query=query.where(User.name.contains(q,autoescape=True))
    return {"items":[member_view(db,u) for u in db.scalars(query.order_by(User.id))]}


@router.put("/members/{identity}")
def update_member(identity:int,payload:MemberPermissionInput,actor=Depends(matrix_admin),db=Depends(get_db)):
    s.guard(db,actor.company_id)
    if actor.role!=Role.COMPANY_ADMIN:s.fail("仅公司管理员可操作",403)
    user=db.get(User,identity)
    if not user or user.company_id!=actor.company_id or user.role not in permissions.ROLES:s.fail("成员不存在",404)
    if user.role==Role.SUPPLY_USER:s.fail("请在公开货盘的货盘用户中设置矩阵权限",404)
    result=set_member_permission(db,actor,user,payload)
    db.commit()
    return result


def set_member_permission(db,actor,user,payload):
    """调用方持有公司锁；两个账号管理入口共用授权及停止运行逻辑。"""
    identity=user.id
    if user.role==Role.COMPANY_ADMIN:s.fail("公司管理员默认拥有管理权限，不能修改",403)
    if not user.is_active and payload.enabled:s.fail("请先在成员管理启用该账号")
    if user.role==Role.SUPPLY_USER and payload.enabled:
        if permissions.supply_user_is_expired(user):s.fail("请先在货盘账号管理为该账号续期")
        if payload.view_scope!="own":s.fail("货盘用户仅可查看本人矩阵数据",422)
    row=db.get(MatrixMemberPermission,identity)
    if payload.expected_revision!=(row.revision if row else 0):s.fail("授权已被修改，请刷新后重试")
    before=permissions.access(db,user)
    if not row:
        row=MatrixMemberPermission(user_id=identity,company_id=actor.company_id,revision=0)
        db.add(row)
    row.enabled=payload.enabled
    row.collect_enabled=payload.enabled
    row.listing_enabled=payload.enabled
    row.view_scope=payload.view_scope if payload.enabled and user.role!=Role.SUPPLY_USER else "own"
    row.revision+=1;row.updated_at=s.utcnow()
    db.flush()
    stopped=[]
    for run in db.scalars(select(MatrixRun).where(MatrixRun.company_id==actor.company_id,MatrixRun.owner_id==identity,MatrixRun.status.in_(s.ACTIVE))):
        if permissions.tasks_allowed(db,user,run.frozen["config"]["tasks"]):continue
        run.stop_requested=True;stopped.append(run.id)
        for item in db.scalars(select(MatrixItem).where(MatrixItem.run_id==run.id,MatrixItem.status=="queued")):
            item.status,item.stage="cancelled","permission_revoked"
        db.add(MatrixCommand(company_id=actor.company_id,agent_id=run.agent_id,kind="stop",payload={"run_id":run.id},expires_at=s.utcnow()+timedelta(minutes=5)))
        s.recompute(db,run)
    s.audit(db,actor,"member.permission",identity,{"before":before,"after":permissions.access(db,user),"stop_requested_runs":stopped})
    return member_view(db,user)


@router.get("/devices")
def devices(user_id:int|None=Query(None,gt=0),actor=Depends(matrix_admin),db=Depends(get_db)):
    query=select(HubAgent).where(HubAgent.company_id==actor.company_id)
    if user_id:query=query.where(HubAgent.user_id==user_id)
    counts=dict(db.execute(select(MatrixAccess.agent_id,func.count(func.distinct(MatrixAccess.environment_id))).where(MatrixAccess.available.is_(True)).group_by(MatrixAccess.agent_id)).all())
    result=[]
    for agent in db.scalars(query.order_by(HubAgent.id.desc())):
        owner=db.get(User,agent.user_id)
        result.append({**s.device_view(db,agent),"permissions":permissions.access(db,owner),"environment_count":counts.get(agent.id,0)})
    return {"items":result}


@router.get("/statistics")
def statistics(start:date|None=None,end:date|None=None,user_id:int|None=Query(None,gt=0),agent_id:int|None=Query(None,gt=0),
    site:Literal["","MY","ID","unknown"]="",task:Literal["","shop.collect","listing.catalog"]="",
    actor=Depends(matrix_admin),db=Depends(get_db)):
    today=(s.utcnow()+timedelta(hours=8)).date()
    start,end=start or today-timedelta(days=6),end or today
    if end<start or (end-start).days>365:s.fail("请选择不超过366天的有效日期范围",422)
    for model,identity in ((User,user_id),(HubAgent,agent_id)):
        if identity:
            row=db.get(model,identity)
            if not row or row.company_id!=actor.company_id:s.fail("筛选对象不存在",404)
    query=select(MatrixRun).where(MatrixRun.company_id==actor.company_id,
        MatrixRun.created_at>=datetime.combine(start,time.min)-timedelta(hours=8),
        MatrixRun.created_at<datetime.combine(end+timedelta(days=1),time.min)-timedelta(hours=8))
    if user_id:query=query.where(MatrixRun.owner_id==user_id)
    if agent_id:query=query.where(MatrixRun.agent_id==agent_id)
    if task:query=query.where(MatrixRun.frozen['config']['tasks'].contains(task))
    if site:
        env_site=func.coalesce(MatrixEnvironment.override_site,MatrixEnvironment.observed_site)
        ids=select(MatrixItem.run_id).join(MatrixEnvironment,MatrixEnvironment.id==MatrixItem.environment_id).where(MatrixItem.company_id==actor.company_id,
            env_site.is_(None) if site=="unknown" else env_site==site)
        query=query.where(MatrixRun.id.in_(ids))
    statuses=Counter();by_member=defaultdict(Counter);by_day=defaultdict(Counter)
    for uid,status,created in db.execute(query.with_only_columns(MatrixRun.owner_id,MatrixRun.status,MatrixRun.created_at).execution_options(yield_per=1000)):
        statuses[status]+=1;by_member[uid][status]+=1;by_day[(created+timedelta(hours=8)).date().isoformat()][status]+=1
    def totals(counts):
        completed=counts['succeeded']+counts['failed']+counts['partial_success']
        return {**{status:counts[status] for status in (*s.ACTIVE,*s.TERMINAL)},"total":sum(counts.values()),"success_rate":counts['succeeded']/completed if completed else None}
    agent_query=select(HubAgent).where(HubAgent.company_id==actor.company_id,HubAgent.is_active.is_(True))
    if user_id:agent_query=agent_query.where(HubAgent.user_id==user_id)
    if agent_id:agent_query=agent_query.where(HubAgent.id==agent_id)
    current_agents=list(db.scalars(agent_query));agent_ids=[a.id for a in current_agents]
    env_query=select(MatrixEnvironment).where(MatrixEnvironment.company_id==actor.company_id,MatrixEnvironment.id.in_(select(MatrixAccess.environment_id).where(MatrixAccess.agent_id.in_(agent_ids),MatrixAccess.available.is_(True))))
    if site:
        env_site=func.coalesce(MatrixEnvironment.override_site,MatrixEnvironment.observed_site)
        env_query=env_query.where(env_site.is_(None) if site=="unknown" else env_site==site)
    env_count=db.scalar(select(func.count()).select_from(env_query.subquery()))
    shop_count=db.scalar(env_query.with_only_columns(func.count(func.distinct(MatrixEnvironment.shop_id))))
    people=list(db.scalars(select(User).where(User.company_id==actor.company_id,User.role.in_(permissions.ROLES))))
    names={u.id:u.name for u in people}
    return {"start":start,"end":end,"summary":totals(statuses),
        "current":{"authorized_members":sum(permissions.access(db,u)['enabled'] for u in people),"devices":len(current_agents),
            "online_devices":sum(bool(a.last_seen_at and a.last_seen_at>s.utcnow()-timedelta(seconds=45)) for a in current_agents),"environments":env_count,"shops":shop_count},
        "by_member":[{"user_id":uid,"name":names.get(uid,"已移除成员"),**totals(counts)} for uid,counts in sorted(by_member.items())],
        "daily":[{"date":(start+timedelta(days=n)).isoformat(),**totals(by_day[(start+timedelta(days=n)).isoformat()])} for n in range((end-start).days+1)]}
