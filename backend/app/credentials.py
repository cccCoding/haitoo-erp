"""第三方账号密钥的静态加密存储。"""
import base64
import hashlib
from cryptography.fernet import Fernet

from .config import get_settings


def _fernet() -> Fernet:
    settings = get_settings()
    secret = settings.credential_encryption_key or settings.secret_key
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()
