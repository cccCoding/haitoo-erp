"""第三方账号密钥的静态加密存储，与 JWT 签名密钥完全隔离。"""
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def _fernet(key_material: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    """新密文始终使用当前凭据密钥，绝不使用 JWT SECRET_KEY。"""
    return _fernet(get_settings().credential_encryption_key).encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """优先使用当前密钥；轮换窗口内允许读取一个明确配置的旧密钥。"""
    settings = get_settings()
    key_materials = [settings.credential_encryption_key]
    if (
        settings.legacy_credential_encryption_key
        and settings.legacy_credential_encryption_key not in key_materials
    ):
        key_materials.append(settings.legacy_credential_encryption_key)

    for key_material in key_materials:
        try:
            return _fernet(key_material).decrypt(value.encode()).decode()
        except InvalidToken:
            continue
    raise InvalidToken("凭据无法使用当前或旧加密密钥解密")
