"""货盘快照到固定文件的桥接；组合预占与平台提交分别记账。"""
import base64
import copy
import secrets
import time
from datetime import timedelta
from sqlalchemy import select
from ..models import SupplyJob, SupplyJobMaterial, User, Company, HubUploadTask, HubUploadAttempt
from ..supply_common import ACTIVE_STATES, digest, user_can_run
from ..supply_files import read_supply_export
from ..supply_quota import QUOTA_VERSION, allocate_links, sku_use_counts
from . import permissions
from .models import MatrixAllocation, MatrixItem, MatrixRun, MatrixEnvironment
from .service import guard, enabled, fail, checked_attempt, utcnow, event


def combination_hash(template_id, materials):
    return digest({"template_id": template_id, "material_ids": sorted(m["id"] for m in materials)})


def reserve_retry(db,item):
    """原文件重试前重新取得原组合；已被其他运行占用的组合绝不重放。"""
    if item.result.get('listing',{}).get('accepted'):
        fail('已有部分商品确认提交，禁止重试整份原文件；请核对未知部分')
    if not item.supply_job_id:return
    job=db.get(SupplyJob,item.supply_job_id)
    if not job or job.state!='completed' or not job.output_expires_at or job.output_expires_at<=utcnow():
        fail('原货盘未生成有效固定文件或文件已过期，请创建新运行',410)
    links=job.checkpoint.get('links',[])
    if len(links)!=job.snapshot['strategy']['link_count']:fail('原文件组合记录不完整')
    for link in links:
        signature=combination_hash(job.template_id,link['materials'])
        row=db.scalar(select(MatrixAllocation).where(MatrixAllocation.shop_id==item.shop_id,MatrixAllocation.combination_hash==signature))
        if not row or row.state=='confirmed' or row.item_id!=item.id and row.state!='released':
            fail('原文件组合已确认提交或被其他运行占用，不能重试；请创建新运行')
        row.item_id,row.state,row.payload=item.id,'prepared',copy.deepcopy(link)


def manual_confirmation(db,item,evidence):
    job=db.get(SupplyJob,item.supply_job_id)
    if not job:fail('原文件组合记录不存在')
    rejected=set(item.result.get('listing',{}).get('rejected',[]))
    links=job.checkpoint.get('links',[])
    if len(links)!=job.snapshot['strategy']['link_count']:fail('原文件组合记录不完整')
    for link in links:
        if link['index'] in rejected:continue
        signature=combination_hash(job.template_id,link['materials'])
        row=db.scalar(select(MatrixAllocation).where(MatrixAllocation.shop_id==item.shop_id,MatrixAllocation.combination_hash==signature))
        if not row or row.item_id!=item.id or row.state=='released':fail('原组合占用记录已变化，不能人工确认')
        row.state='confirmed'
    item.result={**item.result,'manual_confirmation':evidence,'listing':{'accepted':sorted(set(range(len(links)))-rejected),'rejected':sorted(rejected),'receipt':'人工核对：'+evidence}}
    return bool(rejected)


def enqueue(db, item, run):
    guard(db, item.company_id); enabled(db, item.company_id, True)
    owner = db.get(User, run.owner_id)
    permissions.require_tasks(db,owner,run.frozen["config"]["tasks"])
    if not user_can_run(owner, db.get(Company, run.company_id)): fail("任务所有者不可用", 403)
    if not item.shop_id: fail("请先关联本次执行环境")
    if item.supply_job_id: return db.get(SupplyJob, item.supply_job_id)
    if db.scalar(select(SupplyJob.id).where(SupplyJob.company_id == item.company_id, SupplyJob.user_id == run.owner_id, SupplyJob.state.in_(ACTIVE_STATES))):
        item.stage = "waiting_supply"
        return None
    earlier = db.scalar(select(MatrixItem.id).join(MatrixRun, MatrixRun.id == MatrixItem.run_id).where(MatrixRun.owner_id == run.owner_id,
        MatrixItem.status == "running", MatrixItem.stage == "waiting_supply", MatrixItem.id < item.id).limit(1))
    if earlier:
        item.stage = "waiting_supply"
        return None
    env = next(e for e in run.frozen["environments"] if e["id"] == item.environment_id)
    frozen = run.frozen["strategies"][env["site"]]
    params, candidates = copy.deepcopy(frozen["parameters"]), frozen["candidates"]
    seed = secrets.token_hex(16)
    links = []
    occupied = {r.combination_hash: r for r in db.scalars(select(MatrixAllocation).where(MatrixAllocation.shop_id == item.shop_id)).all()}
    used = sku_use_counts(db, item.company_id, run.owner_id, [m["sku"] for m in candidates])
    from ..supply_worker import distinct_sample, style_sample
    deadline = time.monotonic() + 5
    for trial in range(10000):
        if time.monotonic() > deadline: break
        try:
            batch = allocate_links(candidates, params["sku_count"], params["link_count"],
                f"{seed}:{trial}", used, sample=style_sample if trial < 100 else distinct_sample)
        except ValueError as exc:
            fail(str(exc), 422)
        chosen = set()
        for link in batch:
            signature = combination_hash(params["template_id"], link["materials"])
            if signature in chosen or signature in occupied and occupied[signature].state != "released":
                break
            chosen.add(signature)
            link["combination_hash"] = signature
        else:
            links = batch
            break
    if len(links) != params["link_count"]: fail("在组合查找预算内未找到足量未使用商品组合，请调整策略或补充货盘", 422)
    for link in links:
        row = occupied.get(link["combination_hash"])
        if row:
            row.item_id, row.state, row.payload = item.id, "reserved", link
        else:
            db.add(MatrixAllocation(company_id=item.company_id, shop_id=item.shop_id, combination_hash=link["combination_hash"], item_id=item.id, payload=link))
    snap = {"strategy": params, "template": frozen["template"], "template_version": frozen["template_version"],
        "title_engine": "v1", "title_profile": None, "title_market_id": None, "catalog_options": frozen["catalog_options"],
        "catalog_type": frozen["catalog_type"], "candidates": candidates, "seed": seed, "internal_usage": True,
        "expected_rows": frozen["expected_rows"], "user_name": owner.name}
    job = SupplyJob(company_id=item.company_id, user_id=run.owner_id, strategy_id=frozen["strategy_id"],
        template_id=params["template_id"], category_catalog_id=params["category_catalog_id"], idempotency_key=f"matrix-item-{item.id}",
        request_hash=digest(snap), snapshot=snap, category_blob=base64.b64decode(frozen["category_blob"]),
        checkpoint={"links": links, "quota_version": QUOTA_VERSION},
        progress={"links_done": 0, "links_total": params["link_count"]})
    db.add(job); db.flush()
    db.add_all(SupplyJobMaterial(company_id=item.company_id, job_id=job.id, material_id=m["id"], sku=m["sku"], version_hash=m["version_hash"], source="snapshot", link_index=-1, successful=False) for m in candidates)
    item.supply_job_id, item.stage = job.id, "generating_file"
    event(db, item, "listing.preparing", {"job_id": job.id, "links": len(links)})
    return job


def prepare(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    if "listing.catalog" not in run.frozen["config"]["tasks"]: fail("任务不含自动上品")
    if run.stop_requested: fail("任务已请求停止")
    job = enqueue(db, item, run)
    if not job:
        db.commit(); return {"status": "waiting_supply"}
    if job.state != "completed":
        if job.state in {"failed", "cancelled"}: fail(job.error or "货盘生成失败", 422)
        db.commit(); return {"status": job.state, "job_id": job.id, "progress": job.progress}
    if not job.output_expires_at or job.output_expires_at <= utcnow(): fail("货盘文件已过期，请创建新运行", 410)
    if job.output_size > 20 * 1024 * 1024: fail("货盘表格超过20MB", 413)
    if not item.upload_task_id:
        env = db.get(MatrixEnvironment, item.environment_id)
        task = HubUploadTask(company_id=item.company_id, created_by=run.owner_id, agent_id=agent.id, source_kind="supply",
            matrix_item_id=item.id, supply_job_id=job.id, environment_name=env.name, container_code=env.container_code,
            template_id=job.template_id, template_name=job.snapshot["template"]["name"], draft_ids=[],
            export_filename=f"TK矩阵_{item.id}.xlsx", export_sha256=job.output_sha256, export_size=job.output_size,
            export_expires_at=job.output_expires_at, parameters={"source": "supply", "link_count": job.snapshot["strategy"]["link_count"]},
            status="running", stage="file_ready", claim_token=payload.claim_token, lease_expires_at=attempt.lease_until)
        db.add(task); db.flush()
        legacy_attempt = HubUploadAttempt(task_id=task.id, agent_id=agent.id, container_code=env.container_code, environment_name=env.name, number=1)
        db.add(legacy_attempt); db.flush(); task.attempt_id = legacy_attempt.id
        item.upload_task_id = task.id
        from .. import hub
        lock = hub.runtime_guard(db, item.company_id, env.container_code)
        lock.task_id = task.id
        for row in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id == item.id, MatrixAllocation.state == "reserved")): row.state = "prepared"
    task = db.get(HubUploadTask, item.upload_task_id)
    if task.status != "running" or task.claim_token != payload.claim_token:
        from sqlalchemy import func
        legacy_attempt = HubUploadAttempt(task_id=task.id, agent_id=agent.id, container_code=task.container_code, environment_name=task.environment_name,
            number=(db.scalar(select(func.max(HubUploadAttempt.number)).where(HubUploadAttempt.task_id == task.id)) or 0) + 1)
        db.add(legacy_attempt); db.flush(); task.attempt_id = legacy_attempt.id
    task.status, task.claim_token, task.lease_expires_at = "running", payload.claim_token, attempt.lease_until
    item.stage = "file_ready"
    db.commit()
    return {"status": "ready", "filename": task.export_filename, "sha256": task.export_sha256, "size": task.export_size,
        "expires_at": task.export_expires_at, "expected_count": job.snapshot["strategy"]["link_count"]}


def download(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    job = db.get(SupplyJob, item.supply_job_id) if item.supply_job_id else None
    if not job or job.state != "completed" or not job.output_expires_at or job.output_expires_at <= utcnow(): fail("固定文件不可用", 410)
    key, checksum, size = job.output_key, job.output_sha256, job.output_size
    if size > 20 * 1024 * 1024: fail("文件超过20MB", 413)
    db.commit()
    return read_supply_export(key, checksum, size)


def submission(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    enabled(db, item.company_id, True)
    if run.stop_requested: fail("已请求停止，禁止开始提交")
    if not item.upload_task_id or item.submission != "not_started": fail("已提交或状态不确定，禁止再次提交")
    job = db.get(SupplyJob, item.supply_job_id)
    if not job.output_expires_at or job.output_expires_at <= utcnow(): fail("固定文件已过期", 410)
    item.submission, item.stage = "request_sent", "submission_pending"
    task = db.get(HubUploadTask, item.upload_task_id)
    task.stage = "importing"
    for row in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id == item.id)): row.state = "submitting"
    event(db, item, "submission.intent", {"task_id": task.id})
    db.commit()
    return {"persisted": True}


def confirm(db, agent, item_id, payload):
    item, attempt, run = checked_attempt(db, agent, item_id, payload)
    if item.submission not in {"request_sent", "confirmed"}: fail("未记录本次提交意图")
    job = db.get(SupplyJob, item.supply_job_id)
    expected = set(range(job.snapshot["strategy"]["link_count"]))
    accepted, rejected = set(payload.accepted), set(payload.rejected)
    if accepted & rejected or len(accepted) != len(payload.accepted) or len(rejected) != len(payload.rejected) or not (accepted | rejected) <= expected:
        fail("平台逐商品结果无效", 422)
    result = {"accepted": sorted(accepted), "rejected": sorted(rejected), "receipt": payload.receipt}
    if item.submission == "confirmed":
        if item.result.get("listing") != result: fail("上品确认内容冲突")
        return {"status": "confirmed"}
    for row in db.scalars(select(MatrixAllocation).where(MatrixAllocation.item_id == item.id)):
        idx = row.payload["index"]
        row.state = "confirmed" if idx in accepted else "released" if idx in rejected else "unknown"
    item.submission = ("confirmed" if accepted else "rejected") if accepted | rejected == expected else "unknown"
    item.result = {**item.result, "listing": result}
    task = db.get(HubUploadTask, item.upload_task_id)
    task.status = ("completed" if accepted else "failed") if accepted | rejected == expected else "awaiting_attention"
    task.stage = "imported" if accepted == expected else "partial_import"
    task.submitted_at, task.claim_token, task.lease_expires_at = utcnow(), None, None
    if accepted | rejected == expected: task.completed_at = utcnow()
    from .. import hub
    hub.finish_attempt(db, task, task.status)
    event(db, item, "listing.result", {"accepted": len(accepted), "rejected": len(rejected), "unknown": len(expected - accepted - rejected)})
    db.commit()
    return {"status": item.submission, "partial": accepted != expected}
