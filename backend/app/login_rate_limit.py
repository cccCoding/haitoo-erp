"""登录限流：用数据库行锁在所有 API worker 间共享计数。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import math

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .models import LoginRateLimit


IP_LIMIT = 20
IP_WINDOW = timedelta(seconds=60)
EMAIL_FAILURE_LIMIT = 5
EMAIL_WINDOW = timedelta(minutes=15)
LIMIT_MESSAGE = "尝试过于频繁，请稍后再试"
TRUSTED_PROXY_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7",
))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalized_ip(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(value or ""))
    except ValueError:
        return None


def client_ip(request: Request) -> str:
    """只接受可信内部代理提供的单个 IP；直连时忽略所有转发头。"""
    peer = _normalized_ip(request.client.host if request.client else None)
    if get_settings().login_client_ip_source == "auto" and peer and any(
        ipaddress.ip_address(peer) in network for network in TRUSTED_PROXY_NETWORKS
    ):
        for header in ("CF-Connecting-IP", "X-Real-IP"):
            if header in request.headers:
                return _normalized_ip(request.headers[header]) or peer
    return peer or "unknown"


def _key(kind: str, value: str) -> str:
    message = f"login:{kind}:{value}".encode("utf-8")
    return hmac.new(get_settings().secret_key.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _lock_counter(db: Session, key_hash: str, now: datetime) -> LoginRateLimit:
    """先写入占位行获取写锁，再读取计数；SQLite 与 MySQL 均可串行化同一键。"""
    values = {"key_hash": key_hash, "attempts": 0, "expires_at": now}
    dialect = db.get_bind().dialect.name
    if dialect == "sqlite":
        statement = sqlite.insert(LoginRateLimit).values(**values).on_conflict_do_nothing(index_elements=["key_hash"])
    elif dialect in {"mysql", "mariadb"}:
        statement = mysql.insert(LoginRateLimit).values(**values).prefix_with("IGNORE")
    else:
        raise RuntimeError(f"登录限流尚不支持数据库方言 {dialect}")
    db.execute(statement)
    return db.scalar(select(LoginRateLimit).where(LoginRateLimit.key_hash == key_hash).with_for_update())


def _reject(expires_at: datetime, now: datetime) -> None:
    seconds = max(1, math.ceil((expires_at - now).total_seconds()))
    raise HTTPException(429, LIMIT_MESSAGE, headers={"Retry-After": str(seconds)})


def count_ip_attempt(db: Session, ip: str, now: datetime | None = None) -> None:
    now = now or _utcnow()
    counter = _lock_counter(db, _key("ip", ip), now)
    if counter.expires_at <= now:
        counter.attempts = 0
        counter.expires_at = now + IP_WINDOW
    if counter.attempts >= IP_LIMIT:
        expires_at = counter.expires_at
        db.commit()
        _reject(expires_at, now)
    counter.attempts += 1
    db.commit()


def lock_email_failures(db: Session, email: str, now: datetime | None = None) -> LoginRateLimit:
    now = now or _utcnow()
    counter = _lock_counter(db, _key("email", email.strip().casefold()), now)
    if counter.attempts >= EMAIL_FAILURE_LIMIT and counter.expires_at > now:
        expires_at = counter.expires_at
        db.commit()
        _reject(expires_at, now)
    return counter


def record_email_failure(db: Session, counter: LoginRateLimit, now: datetime | None = None) -> None:
    now = now or _utcnow()
    if counter.attempts == 0 or counter.expires_at <= now:
        counter.attempts = 0
        counter.expires_at = now + EMAIL_WINDOW
    counter.attempts += 1
    db.commit()


def clear_email_failures(db: Session, counter: LoginRateLimit) -> None:
    counter.attempts = 0
    counter.expires_at = _utcnow()
    db.commit()


def cleanup_expired_login_counters() -> None:
    """每次最多清理一批，避免长期运行时计数表无限增长。"""
    with SessionLocal() as db:
        while True:
            keys = db.scalars(
                select(LoginRateLimit.key_hash)
                .where(LoginRateLimit.expires_at < _utcnow())
                .limit(1000)
            ).all()
            if not keys:
                return
            db.execute(delete(LoginRateLimit).where(LoginRateLimit.key_hash.in_(keys)))
            db.commit()
            if len(keys) < 1000:
                return
