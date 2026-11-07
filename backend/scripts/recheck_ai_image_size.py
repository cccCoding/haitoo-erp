"""重新检查因旧 3 MiB 上限被拒绝的直存候选图；默认仅预览。"""
import argparse
from collections import Counter
from datetime import timedelta

from sqlalchemy import select

from app import ai_image_storage as storage
from app.ai_images import now
from app.database import SessionLocal
from app.models import AIImageCandidate, PodTask, TaskStatus

OLD_ERROR = "图片为空或超过 3 MiB"


def run(session_factory=SessionLocal, *, apply=False):
    client, bucket, _, base, _ = storage.configuration()
    counts = Counter()
    last_id = 0
    while True:
        with session_factory() as db:
            rows = db.execute(select(AIImageCandidate.id, AIImageCandidate.task_id,
                AIImageCandidate.company_id, AIImageCandidate.run_id, AIImageCandidate.bucket,
                AIImageCandidate.object_key, AIImageCandidate.source_url).where(
                AIImageCandidate.id > last_id, AIImageCandidate.state == "invalid",
                AIImageCandidate.error == OLD_ERROR).order_by(AIImageCandidate.id).limit(200)).all()
        if not rows:
            break
        for row in rows:
            last_id = row.id
            try:
                with session_factory() as db:
                    task = db.get(PodTask, row.task_id)
                    context = dict(task.storage_context or {}) if task else {}
                    if (not task or task.company_id != row.company_id or task.status != TaskStatus.AWAITING_SELECTION
                            or context.get("mode") != "direct" or context.get("run_id") != row.run_id
                            or context.get("bucket") != row.bucket or row.bucket != bucket
                            or storage.key_from_url(row.source_url, base) != row.object_key
                            or not row.object_key.startswith(context.get("path", "") + "/")):
                        counts["跳过任务或路径不匹配"] += 1
                        continue
                size, mime, uploaded, etag = storage.metadata(storage.head(client, row.bucket, row.object_key), row.object_key)
                expires = uploaded + timedelta(days=30)
                if expires <= now():
                    counts["已过期"] += 1
                    continue
                if apply:
                    with session_factory() as db:
                        task = db.scalar(select(PodTask).where(PodTask.id == row.task_id).with_for_update())
                        candidate = db.scalar(select(AIImageCandidate).where(AIImageCandidate.id == row.id).with_for_update())
                        if (not task or task.status != TaskStatus.AWAITING_SELECTION or task.company_id != row.company_id
                                or (task.storage_context or {}) != context or not candidate
                                or candidate.state != "invalid" or candidate.error != OLD_ERROR
                                or candidate.run_id != row.run_id or candidate.source_url != row.source_url
                                or candidate.bucket != row.bucket or candidate.object_key != row.object_key
                                or candidate.image_file_id is not None):
                            counts["状态已变化"] += 1
                            continue
                        candidate.size_bytes, candidate.mime_type = size, mime
                        candidate.uploaded_at, candidate.expires_at, candidate.etag = uploaded, expires, etag
                        candidate.state, candidate.error = "pending", None
                        db.commit()
                counts["已恢复" if apply else "可恢复"] += 1
            except storage.InvalidCandidate as exc:
                counts["仍无效或已过期"] += 1
                print(f"候选图 {row.id}：{exc}")
            except Exception as exc:
                counts["检查失败"] += 1
                print(f"候选图 {row.id}：检查失败（{type(exc).__name__}）")
    for label, count in sorted(counts.items()):
        print(f"{label}：{count}")
    if not counts:
        print("没有需要重新检查的候选图")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="将通过检查的候选图恢复为待审核")
    args = parser.parse_args()
    result = run(apply=args.apply)
    if result["检查失败"]:
        raise SystemExit(1)
