"""持久化货盘 Worker：短事务租约、独立续租、检查点和执行版本隔离。"""
import asyncio
import copy
import logging
import random
from contextlib import suppress
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import aliased

from .config import get_settings
from .credentials import decrypt_secret
from .ai_providers import DEEPSEEK_TITLE_MODEL, ProviderError, validate_generated_title
from .database import SessionLocal
from .models import Company, ProductTemplate, SupplyJob, SupplyJobMaterial, User
from .supply_common import (ACTIVE_STATES, digest, eligible_materials,
    lock_company, normalize_title, now, sizes, template_snapshot,
    template_version, unique_title, user_can_run)
from .supply_files import delete_supply_export, list_supply_exports, upload_supply_export
from .image_files import resolve_export_images
from .tiktok_export import build_workbook

logger = logging.getLogger(__name__)
RETRY_DELAYS = (2, 5, 15)


class LostLease(Exception):
    pass


def distinct_sample(candidates, count, rng):
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    selected, ids, skus, urls = [], set(), set(), set()
    for candidate in shuffled:
        if candidate["id"] in ids or candidate["sku"] in skus or candidate["url"] in urls:
            continue
        selected.append(copy.deepcopy(candidate))
        ids.add(candidate["id"]); skus.add(candidate["sku"]); urls.add(candidate["url"])
        if len(selected) == count:
            break
    return selected


def style_sample(candidates, count, rng):
    """优先同风格，混用时选最大可用分组，未分组仅在最后补齐。"""
    groups, ungrouped = {}, []
    for candidate in candidates:
        style_id = candidate.get("style_id")
        if type(style_id) is int and style_id > 0:
            groups.setdefault(style_id, []).append(candidate)
        else:
            ungrouped.append(candidate)
    # 旧快照及全部未分组的任务保留原有随机顺序。
    if not groups:
        return distinct_sample(candidates, count, rng)

    samples = {style_id: distinct_sample(items, count, rng) for style_id, items in groups.items()}
    complete = [items for items in samples.values() if len(items) == count]
    if complete:
        return rng.choice(complete)

    selected, ids, skus, urls = [], set(), set(), set()

    def available(items):
        return [item for item in items
                if item["id"] not in ids and item["sku"] not in skus and item["url"] not in urls]

    def add(items):
        selected.extend(items)
        for item in items:
            ids.add(item["id"]); skus.add(item["sku"]); urls.add(item["url"])

    while samples:
        largest = max(len(items) for items in samples.values())
        if not largest:
            break
        style_id = rng.choice([key for key, items in samples.items() if len(items) == largest])
        add(samples[style_id])
        if len(selected) == count:
            return selected
        del groups[style_id]
        samples = {key: distinct_sample(available(items), count - len(selected), rng)
                   for key, items in groups.items()}
    add(distinct_sample(available(ungrouped), count - len(selected), rng))
    if len(selected) == count:
        return selected
    # 风格优先的贪心选择可能与其他图片冲突，退回原有全量随机去重方案。
    return distinct_sample(candidates, count, rng)


def _cancel(job, message):
    job.state, job.stage, job.error, job.completed_at = "cancelled", "cancelled", message, now()
    job.lease_owner, job.lease_expires_at = None, None
    job.export_blob = None
    job.lease_epoch += 1


def claim_job(session_factory=SessionLocal, owner=None):
    owner = owner or uuid4().hex
    at = now()
    with session_factory() as db:
        running_job = aliased(SupplyJob)
        occupied = select(func.count()).select_from(running_job).where(
            running_job.company_id == SupplyJob.company_id,
            running_job.state.in_(ACTIVE_STATES), running_job.lease_expires_at > at
        ).correlate(SupplyJob).scalar_subquery()
        candidates = db.execute(select(SupplyJob.id, SupplyJob.company_id).where(
            SupplyJob.state.in_(ACTIVE_STATES), or_(SupplyJob.available_at.is_(None), SupplyJob.available_at <= at),
            or_(SupplyJob.lease_expires_at.is_(None), SupplyJob.lease_expires_at <= at),
            occupied < get_settings().supply_company_concurrency,
        ).order_by(SupplyJob.created_at, SupplyJob.id).limit(100)).all()
    for job_id, company_id in candidates:
        with session_factory() as db:
            company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
            job = db.scalar(select(SupplyJob).where(SupplyJob.id == job_id).with_for_update())
            if not job or job.state not in ACTIVE_STATES or (
                job.lease_expires_at and job.lease_expires_at > now()) or (job.available_at and job.available_at > now()):
                continue
            user = db.scalar(select(User).where(User.id == job.user_id).with_for_update())
            if not user_can_run(user, company):
                _cancel(job, "账号不可用")
                db.commit()
                continue
            running = db.scalar(select(func.count()).select_from(SupplyJob).where(
                SupplyJob.company_id == company_id, SupplyJob.state.in_(ACTIVE_STATES),
                SupplyJob.lease_expires_at > now())) or 0
            if running >= get_settings().supply_company_concurrency:
                continue
            job.lease_epoch += 1
            job.lease_owner = owner
            job.lease_expires_at = now() + timedelta(seconds=get_settings().supply_lease_seconds)
            job.state = "running"
            job.available_at = None
            epoch = job.lease_epoch
            db.commit()
            return job_id, epoch, owner
    return None


def mutate(job_id, epoch, owner, callback, session_factory=SessionLocal):
    with session_factory() as db:
        company_id = db.scalar(select(SupplyJob.company_id).where(SupplyJob.id == job_id))
        if company_id is None:
            raise LostLease()
        db.rollback()
        company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
        job = db.scalar(select(SupplyJob).where(SupplyJob.id == job_id).with_for_update())
        if not job or job.state != "running" or job.lease_epoch != epoch or job.lease_owner != owner or (
                not job.lease_expires_at or job.lease_expires_at <= now()):
            raise LostLease()
        user = db.scalar(select(User).where(User.id == job.user_id).with_for_update())
        if not user_can_run(user, company):
            _cancel(job, "账号不可用")
            db.commit()
            raise LostLease()
        result = callback(db, job)
        db.commit()
        return result


def checkpoint(job_id, epoch, owner, change, session_factory=SessionLocal, stage=None):
    def apply(db, job):
        value = copy.deepcopy(job.checkpoint or {})
        change(value, db, job)
        job.checkpoint = value
        if stage:
            job.stage = stage
        return copy.deepcopy(value)
    return mutate(job_id, epoch, owner, apply, session_factory)


async def request_title(api_key, template, requirements):
    settings = get_settings()
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        response = await client.post(f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"}, json={"model": DEEPSEEK_TITLE_MODEL,
                "thinking": {"type": "disabled"},
                "messages": [{"role": "system", "content": "Write one factual English TikTok product title, 25-220 characters. Return only the title. Do not invent brand, material, pattern, medical claims or benefits."},
                    {"role": "user", "content": f"Product: {template.get('name', '')}\nFacts: {template.get('product_description', '')}\nTemplate requirements: {template.get('title_template') or ''}\nAdditional requirements: {requirements}"}],
                "temperature": 0.7})
        response.raise_for_status()
        choice = response.json()["choices"][0]
        value = choice["message"]["content"]
        if not isinstance(value, str) or choice.get("finish_reason", "stop") != "stop":
            raise ValueError("AI 标题格式不符合要求")
        return validate_generated_title(value.strip())


async def request_market_title(job_id, epoch, index, first_image, session_factory):
    from .title_models import TitleMarket, TitleRecord
    from .title_service import create_record, generate_record, task_still_active, validate_malay_title
    with session_factory() as db:
        job = db.get(SupplyJob, job_id)
        market = db.get(TitleMarket, job.snapshot['title_market_id'])
        profile = copy.deepcopy(job.snapshot['title_profile'])
        profile.update(supply_job_id=job_id, supply_epoch=epoch,
            additional_requirements=job.snapshot['strategy'].get('title_requirements', ''))
        record = create_record(db, market, job.user_id, profile, first_image,
            ['supply', job_id, index], supply=True)
        # 执行 epoch 是权限检查，不改变已固定的商品、词库或策略。
        record.snapshot = {**record.snapshot, 'supply_epoch': epoch}
        db.commit()
        try:
            result = await generate_record(db, record.id)
        except ProviderError as exc:
            task_still_active(db, record)
            db.refresh(record)
            if record.lease_owner or any(word in str(exc) for word in ('执行权', '取消', '正在生成', '账号')):
                raise
            fallback = validate_malay_title(profile['fallback_title'], 220)
            record = db.get(TitleRecord, record.id, populate_existing=True)
            record.title = fallback
            record.source = 'fallback'
            record.state = 'generated'
            record.selected_keywords = []
            record.warnings = ['已使用审核的马来语兜底标题；可能与其他链接高度相似']
            db.commit()
            result = {'title': fallback, 'source': 'fallback', 'warnings': record.warnings}
        return {**result, 'generation_id': record.id}


async def run_job(job_id, epoch, owner, session_factory=SessionLocal):
    settings = get_settings()
    dead = asyncio.Event()
    title_semaphore = asyncio.Semaphore(settings.supply_title_concurrency)
    uploaded_key = None

    def save(change, stage=None):
        if dead.is_set():
            raise LostLease()
        return checkpoint(job_id, epoch, owner, change, session_factory, stage)

    async def heartbeat():
        while True:
            await asyncio.sleep(settings.supply_heartbeat_seconds)
            try:
                mutate(job_id, epoch, owner, lambda db, job: setattr(job, "lease_expires_at",
                    now() + timedelta(seconds=settings.supply_lease_seconds)), session_factory)
            except Exception:
                dead.set()
                return

    beat = asyncio.create_task(heartbeat())
    try:
        data = mutate(job_id, epoch, owner, lambda db, job: {
            "snapshot": copy.deepcopy(job.snapshot), "checkpoint": copy.deepcopy(job.checkpoint),
            "company_id": job.company_id, "export_blob": job.export_blob,
            "secret": db.get(Company, job.company_id).supply_ai_secret_encrypted,
        }, session_factory)
        snap, company_id = data["snapshot"], data["company_id"]
        strategy, template = snap["strategy"], snap["template"]

        if not data["checkpoint"].get("links"):
            candidates = snap["candidates"]
            rng = random.Random(snap["seed"])
            links = []
            for index in range(strategy["link_count"]):
                group = style_sample(candidates, strategy["sku_count"], rng)
                if len(group) != strategy["sku_count"]:
                    raise ValueError("没有足够素材组成完整商品组")
                links.append({"index": index, "materials": group, "title": None, "replaced": False})
            save(lambda value, db, job: value.update(links=links), "titles")

        if not data["export_blob"]:
            try:
                api_key = decrypt_secret(data["secret"]) if data["secret"] else None
            except Exception:
                api_key = None

            async def generate(index):
                async with title_semaphore:
                    if snap.get('title_engine') == 'v2':
                        state = save(lambda value, db, job: None)
                        link = state['links'][index]
                        if link.get('title'):
                            return
                        result = await request_market_title(job_id, epoch, index, link['materials'][0]['url'], session_factory)
                        title = result['title'] + f" - L{index + 1:02d}"
                        def complete_market(value, db, job):
                            value['links'][index].update(title=title, title_source=result.get('source', 'ai'),
                                generation_id=result['generation_id'], title_warnings=result.get('warnings', []))
                            job.progress = {'links_total': strategy['link_count'],
                                'links_done': sum(bool(row.get('title')) for row in value['links'])}
                        save(complete_market)
                        return
                    while True:
                        state = save(lambda value, db, job: None)
                        if state["links"][index].get("title"):
                            return
                        count = state.get("title_attempts", {}).get(str(index), 0)
                        result = None
                        if api_key and count < 4:
                            def consume(value, db, job):
                                value.setdefault("title_attempts", {})[str(index)] = count + 1
                            save(consume, "titles")
                            try:
                                result = await request_title(api_key, template, strategy.get("title_requirements", ""))
                            except Exception:
                                if count < 3:
                                    await asyncio.sleep(RETRY_DELAYS[count])
                                    continue
                        title = unique_title(result, template["supply_fallback_title"], index)
                        def complete(value, db, job):
                            value["links"][index]["title"] = title
                            value["links"][index]["title_source"] = "ai" if result else "fallback"
                            job.progress = {"links_total": strategy["link_count"],
                                "links_done": sum(bool(link.get("title")) for link in value["links"])}
                        save(complete)
                        return
            await asyncio.gather(*(generate(index) for index in range(strategy["link_count"])))

            chart = (template.get("size_chart_url") or "").strip()
            state = save(lambda value, db, job: None, "excel")
            links = state["links"]
            titles = [normalize_title(link["title"]) for link in links]
            if len(set(titles)) != len(titles) or any(not 25 <= len(link["title"]) <= 255 for link in links):
                raise ValueError("最终商品标题重复或长度不符合要求")
            if len(links) != strategy["link_count"]:
                raise ValueError("最终商品组数量不足")
            products = []
            for link in links:
                group = link["materials"]
                if len(group) != strategy["sku_count"] or any(len({item[field] for item in group}) != len(group)
                    for field in ("id", "sku", "url")):
                    raise ValueError("最终 SKU 数量不足或重复")
                products.append({"title": link["title"], "description": template["product_description"],
                    "image_urls": [item["url"] for item in group],
                    "sku_images": [{"image_url": item["url"], "sku": item["sku"]} for item in group],
                    "size_chart_url": chart or None, "price": Decimal(strategy["price"]), "quantity": strategy["stock"]})
            if sum(len(product["sku_images"]) * len(sizes(template)) for product in products) > 4994:
                raise ValueError("最终数据超过 4,994 行")
            with session_factory() as db:
                resolve_export_images(db, company_id, products)
                category_blob = bytes(db.get(SupplyJob, job_id).category_blob)
            content = await asyncio.to_thread(build_workbook, template=SimpleNamespace(**template),
                category=strategy["category_name"], cod=strategy["cod"], attributes=strategy["attributes"],
                products=products, template_bytes=category_blob, template_type=snap["catalog_type"],
                shipping_insurance=strategy.get("shipping_insurance"))
            mutate(job_id, epoch, owner, lambda db, job: setattr(job, "export_blob", content), session_factory)
        else:
            content = data["export_blob"]

        def upload_budget(db, job):
            if job.upload_attempts >= 4:
                raise ValueError("R2 上传重试次数已用尽")
            job.upload_attempts += 1
            job.stage = "upload"
            return job.upload_attempts
        attempt = mutate(job_id, epoch, owner, upload_budget, session_factory)
        try:
            uploaded = await asyncio.to_thread(upload_supply_export, company_id, job_id, epoch,
                f"TikTok货盘_{job_id}.xlsx", content)
            uploaded_key = uploaded["key"]
        except Exception:
            def retry(db, job):
                if attempt >= 4:
                    job.state, job.stage, job.error, job.completed_at = "failed", "failed", "R2 上传失败，重试次数已用尽", now()
                    job.export_blob = None
                else:
                    job.state, job.stage = "retry_wait", "upload"
                    job.available_at = now() + timedelta(seconds=RETRY_DELAYS[attempt - 1])
                    job.error = "R2 上传暂时失败，等待重试"
                job.lease_owner, job.lease_expires_at = None, None
            mutate(job_id, epoch, owner, retry, session_factory)
            return

        def complete(db, job):
            for link in job.checkpoint["links"]:
                if link.get('generation_id'):
                    from .title_models import TitleRecord
                    from .title_service import count_adopted_keywords
                    record = db.get(TitleRecord, link['generation_id'])
                    if record and not record.adopted_at:
                        record.adopted_at = now()
                        record.state = 'adopted'
                        count_adopted_keywords(db, record, record.title)
                for item in link["materials"]:
                    db.add(SupplyJobMaterial(company_id=company_id, job_id=job_id,
                        material_id=item["id"], version_hash=item["version_hash"],
                        source="replacement" if item["version_hash"] not in {candidate["version_hash"] for candidate in snap["candidates"]} else "snapshot",
                        link_index=link["index"], successful=True))
            job.output_key, job.output_sha256, job.output_size = uploaded["key"], uploaded["sha256"], uploaded["size"]
            job.output_expires_at = now() + timedelta(days=settings.supply_file_retention_days)
            job.state, job.stage, job.completed_at, job.error = "completed", "completed", now(), None
            job.export_blob = None
            job.lease_owner, job.lease_expires_at = None, None
            job.progress = {**(job.progress or {}), "links_done": strategy["link_count"], "links_total": strategy["link_count"]}
        mutate(job_id, epoch, owner, complete, session_factory)
        uploaded_key = None
    except LostLease:
        logger.info("货盘执行停止 | job=%s epoch=%s", job_id, epoch)
    except Exception as exc:
        logger.warning("货盘任务失败 | job=%s error_type=%s", job_id, type(exc).__name__)
        def fail(db, job):
            job.state, job.stage, job.completed_at = "failed", "failed", now()
            job.error = str(exc)[:500] if isinstance(exc, (ValueError, HTTPException)) else "生成失败，请联系管理员或重新提交"
            job.lease_owner, job.lease_expires_at, job.export_blob = None, None, None
        with suppress(LostLease):
            mutate(job_id, epoch, owner, fail, session_factory)
    finally:
        beat.cancel()
        with suppress(asyncio.CancelledError):
            await beat
        if uploaded_key:
            with suppress(Exception):
                await asyncio.to_thread(delete_supply_export, uploaded_key)


def cancel_ineligible_jobs(session_factory=SessionLocal):
    with session_factory() as db:
        companies = db.scalars(select(Company.id).where(Company.id.in_(
            select(SupplyJob.company_id).where(SupplyJob.state.in_(ACTIVE_STATES))))).all()
    for company_id in companies:
        with session_factory() as db:
            company = db.scalar(select(Company).where(Company.id == company_id).with_for_update())
            jobs = db.scalars(select(SupplyJob).where(SupplyJob.company_id == company_id,
                SupplyJob.state.in_(ACTIVE_STATES)).with_for_update()).all()
            for job in jobs:
                if not user_can_run(db.get(User, job.user_id), company):
                    _cancel(job, "账号不可用")
            db.commit()


def cleanup_exports(session_factory=SessionLocal):
    with session_factory() as db:
        expired = db.execute(select(SupplyJob.id, SupplyJob.output_key).where(
            SupplyJob.output_expires_at <= now(), SupplyJob.output_deleted_at.is_(None),
            SupplyJob.output_key.is_not(None))).all()
    for job_id, key in expired:
        try:
            delete_supply_export(key)
        except Exception:
            logger.warning("货盘过期文件清理失败 | job=%s", job_id)
            continue
        with session_factory() as db:
            job = db.get(SupplyJob, job_id)
            if job and job.output_key == key:
                job.output_deleted_at = now()
                db.commit()
    with session_factory() as db:
        referenced = set(db.scalars(select(SupplyJob.output_key).where(SupplyJob.output_key.is_not(None),
            SupplyJob.output_deleted_at.is_(None))).all())
    try:
        for key in list_supply_exports(now() - timedelta(days=1)):
            if key not in referenced:
                delete_supply_export(key)
    except Exception:
        logger.warning("货盘孤立文件清理暂时失败")


async def run_cycle(session_factory=SessionLocal):
    cancel_ineligible_jobs(session_factory)
    claimed = claim_job(session_factory)
    if claimed is None:
        return 0
    await run_job(*claimed, session_factory=session_factory)
    return 1


async def run_forever():
    last_cleanup = None
    running = set()
    while True:
        try:
            cancel_ineligible_jobs()
            if last_cleanup is None or (now() - last_cleanup).total_seconds() >= 3600:
                await asyncio.to_thread(cleanup_exports)
                last_cleanup = now()
            running = {task for task in running if not task.done()}
            while len(running) < get_settings().supply_worker_concurrency:
                claimed = claim_job()
                if claimed is None:
                    break
                task = asyncio.create_task(run_job(*claimed))
                running.add(task)
        except Exception:
            logger.exception("货盘队列轮询失败")
        await asyncio.sleep(2)


def main():
    from .database import engine
    from .logging_config import configure_logging
    from .schema_version import assert_schema_current
    configure_logging()
    assert_schema_current(engine)
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
