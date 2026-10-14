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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from .config import get_settings
from .credentials import decrypt_secret
from .ai_providers import DEEPSEEK_TITLE_MODEL, validate_generated_title
from .database import SessionLocal
from .models import Company, ProductTemplate, SupplyJob, SupplyJobMaterial, User
from .supply_common import (ACTIVE_STATES, BAD_HEALTH, begin_check, digest, eligible_materials,
    finish_check, health_records, lock_company, normalize_title, now, sizes, template_snapshot,
    template_version, unique_title, user_can_run)
from .supply_files import delete_supply_export, list_supply_exports, upload_supply_export
from .supply_images import check_image
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


async def run_job(job_id, epoch, owner, session_factory=SessionLocal):
    settings = get_settings()
    dead = asyncio.Event()
    image_semaphore = asyncio.Semaphore(settings.supply_image_concurrency)
    title_semaphore = asyncio.Semaphore(settings.supply_title_concurrency)
    image_futures = {}
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
            with session_factory() as db:
                health = health_records(db, company_id, [item["url"] for item in snap["candidates"]])
            candidates = [item for item in snap["candidates"] if item["url"] not in health
                          or health[item["url"]].status not in BAD_HEALTH]
            rng = random.Random(snap["seed"])
            links = []
            for index in range(strategy["link_count"]):
                group = distinct_sample(candidates, strategy["sku_count"], rng)
                if len(group) != strategy["sku_count"]:
                    raise ValueError("没有足够的未标记失效素材组成完整商品组")
                links.append({"index": index, "materials": group, "title": None, "replaced": False})
            save(lambda value, db, job: value.update(links=links), "titles")

        if not data["export_blob"]:
            try:
                api_key = decrypt_secret(data["secret"]) if data["secret"] else None
            except Exception:
                api_key = None

            async def generate(index):
                async with title_semaphore:
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

            async def probe(url):
                async with image_semaphore:
                    key = digest(url)
                    while True:
                        state = save(lambda value, db, job: None, "images")
                        record = state.get("image_checks", {}).get(key, {})
                        if record.get("result") and record.get("result_epoch") == epoch:
                            return record["result"]
                        attempts = record.get("attempts", 0)
                        if attempts >= 3:
                            result = {"status": "check_failed", "reason": "检查次数已用尽或检查中断"}
                        else:
                            def consume(value, db, job):
                                value.setdefault("image_checks", {})[key] = {"url": url, "attempts": attempts + 1}
                            save(consume)
                            with session_factory() as db:
                                sequence = begin_check(db, company_id, url)
                            try:
                                result = await check_image(url)
                            except Exception:
                                result = {"status": "check_failed", "reason": "图片检查服务暂时不可用"}
                            with session_factory() as db:
                                finish_check(db, company_id, url, sequence, result)
                            if result["status"] == "check_failed" and attempts < 2:
                                await asyncio.sleep(RETRY_DELAYS[attempts])
                                continue
                        def complete(value, db, job):
                            value.setdefault("image_checks", {}).setdefault(key, {"url": url, "attempts": attempts})["result"] = result
                            value["image_checks"][key]["result_epoch"] = epoch
                            checks = value["image_checks"]
                            job.progress = {**(job.progress or {}), "images_checked": sum(bool(item.get("result")) for item in checks.values()),
                                "images_total": len(checks)}
                        save(complete)
                        return result

            async def checked(url):
                if url not in image_futures:
                    image_futures[url] = asyncio.create_task(probe(url))
                return await image_futures[url]

            state = save(lambda value, db, job: None)
            urls = list(dict.fromkeys(item["url"] for link in state["links"] for item in link["materials"]))
            chart = (template.get("size_chart_url") or "").strip()
            if chart:
                urls.append(chart)
            await asyncio.gather(*(checked(url) for url in set(urls)))
            if chart and (await checked(chart))["status"] != "available":
                raise ValueError("模板尺码图不可用，请修复后重新提交")

            for index in range(strategy["link_count"]):
                for position in range(strategy["sku_count"]):
                    state = save(lambda value, db, job: None)
                    original = state["links"][index]["materials"][position]
                    if (await checked(original["url"]))["status"] == "available":
                        continue
                    current = state["links"][index]["materials"]
                    peers = [item for pos, item in enumerate(current) if pos != position]
                    forbidden_ids, forbidden_skus, forbidden_urls = (
                        {item[field] for item in peers} for field in ("id", "sku", "url"))
                    acquired = list(state.get("replacement_candidates", {}).values())
                    checked_good = [item for item in snap["candidates"] + acquired if item["url"] in image_futures
                        and image_futures[item["url"]].done() and not image_futures[item["url"]].cancelled()
                        and image_futures[item["url"]].result()["status"] == "available"]
                    with session_factory() as db:
                        live_template = db.get(ProductTemplate, template["id"])
                        live = eligible_materials(db, company_id, template["id"], snap["template_version"]) if (
                            live_template and live_template.company_id == company_id and live_template.supply_public
                            and template_version(template_snapshot(live_template)) == snap["template_version"]) else []
                    rng = random.Random(f"{snap['seed']}:{index}:{position}")
                    old_candidates, new_candidates = list(snap["candidates"]) + acquired, list(live)
                    rng.shuffle(old_candidates); rng.shuffle(new_candidates)
                    replacement = None
                    position_key = f"{index}:{position}"
                    for candidate in checked_good + old_candidates + new_candidates:
                        if candidate["id"] in forbidden_ids or candidate["sku"] in forbidden_skus or candidate["url"] in forbidden_urls:
                            continue
                        if candidate["version_hash"] == original["version_hash"]:
                            continue
                        state = save(lambda value, db, job: None)
                        record = state.get("replacement_attempts", {}).get(position_key, {"tried": []})
                        if candidate["version_hash"] in record["tried"]:
                            # 已检查成功但尚未来得及提交替换的候选，在恢复后仍可提交。
                            prior = state.get("image_checks", {}).get(digest(candidate["url"]), {}).get("result")
                            if prior and prior["status"] == "available" and (await checked(candidate["url"]))["status"] == "available":
                                replacement = candidate
                                break
                            continue
                        if len(record["tried"]) >= 10:
                            break
                        def register(value, db, job):
                            if candidate not in snap["candidates"] and candidate not in acquired:
                                current_template = db.get(ProductTemplate, template["id"])
                                from .models import MaterialAsset
                                asset = db.get(MaterialAsset, candidate["id"])
                                if (not asset or asset.company_id != company_id or not asset.supply_listed
                                    or not current_template or not current_template.supply_public
                                    or template_version(template_snapshot(current_template)) != snap["template_version"]
                                    or asset.template_id != template["id"]
                                    or asset.url != candidate["url"] or asset.sku != candidate["sku"]):
                                    return False
                            value.setdefault("replacement_attempts", {}).setdefault(position_key, {"tried": []})["tried"].append(candidate["version_hash"])
                            association = db.scalar(select(SupplyJobMaterial.id).where(SupplyJobMaterial.job_id == job_id,
                                SupplyJobMaterial.material_id == candidate["id"], SupplyJobMaterial.version_hash == candidate["version_hash"],
                                SupplyJobMaterial.link_index == -1))
                            if not association:
                                db.add(SupplyJobMaterial(company_id=company_id, job_id=job_id,
                                    material_id=candidate["id"], version_hash=candidate["version_hash"], source="replacement", link_index=-1))
                            value.setdefault("replacement_candidates", {})[candidate["version_hash"]] = copy.deepcopy(candidate)
                            return True
                        registered = [False]
                        def register_change(value, db, job):
                            registered[0] = register(value, db, job)
                        save(register_change)
                        if not registered[0]:
                            continue
                        if (await checked(candidate["url"]))["status"] == "available":
                            replacement = candidate
                            break
                    if replacement is None:
                        raise ValueError("图片失效且替换素材不足；未生成残缺表格")
                    def replace(value, db, job):
                        link = value["links"][index]
                        link["materials"][position] = copy.deepcopy(replacement)
                        link["replaced"] = True
                        link["title"] = unique_title(None, template["supply_fallback_title"], index)
                        link["title_source"] = "fallback_after_replacement"
                    save(replace)

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
                if any(state["image_checks"][digest(item["url"])]["result"]["status"] != "available"
                    or state["image_checks"][digest(item["url"])].get("result_epoch") != epoch for item in group):
                    raise ValueError("最终图片检查未通过")
                products.append({"title": link["title"], "description": template["product_description"],
                    "image_urls": [item["url"] for item in group],
                    "sku_images": [{"image_url": item["url"], "sku": item["sku"]} for item in group],
                    "size_chart_url": chart or None, "price": Decimal(strategy["price"]), "quantity": strategy["stock"]})
            if chart and state["image_checks"][digest(chart)].get("result_epoch") != epoch:
                raise ValueError("尺码图检查结果属于已过期的执行版本")
            if sum(len(product["sku_images"]) * len(sizes(template)) for product in products) > 4994:
                raise ValueError("最终数据超过 4,994 行")
            with session_factory() as db:
                category_blob = bytes(db.get(SupplyJob, job_id).category_blob)
            content = await asyncio.to_thread(build_workbook, template=SimpleNamespace(**template),
                category=strategy["category_name"], cod=strategy["cod"], attributes=strategy["attributes"],
                products=products, template_bytes=category_blob, template_type=snap["catalog_type"])
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
        for task in image_futures.values():
            if not task.done():
                task.cancel()
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
