"""第三方凭据加密密钥轮换命令。"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .credentials import decrypt_secret, encrypt_secret
from .database import SessionLocal
from .models import Company, UserAIProviderCredential


def rotate_stored_credentials(db: Session) -> tuple[int, int]:
    """在单个数据库事务中解密并重新加密全部第三方凭据。"""
    company_count = 0
    for company in db.scalars(select(Company).where(Company.miaoshou_secret_encrypted.is_not(None))):
        company.miaoshou_secret_encrypted = encrypt_secret(
            decrypt_secret(company.miaoshou_secret_encrypted)
        )
        company_count += 1

    user_credential_count = 0
    for credential in db.scalars(select(UserAIProviderCredential)):
        credential.secret_encrypted = encrypt_secret(decrypt_secret(credential.secret_encrypted))
        user_credential_count += 1

    db.flush()
    return company_count, user_credential_count


def run() -> None:
    settings = get_settings()
    if not settings.legacy_credential_encryption_key:
        raise RuntimeError("未配置 LEGACY_CREDENTIAL_ENCRYPTION_KEY，拒绝执行密钥轮换")
    if settings.legacy_credential_encryption_key == settings.credential_encryption_key:
        raise RuntimeError("新旧凭据加密密钥不能相同")

    with SessionLocal.begin() as db:
        company_count, user_credential_count = rotate_stored_credentials(db)
    print(
        "凭据重加密完成："
        f"妙手账号 {company_count} 条，员工 AI 密钥 {user_credential_count} 条。"
        "验证业务正常后，请删除 LEGACY_CREDENTIAL_ENCRYPTION_KEY。"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="轮换 Haitoro 第三方凭据加密密钥")
    parser.parse_args()
    run()
