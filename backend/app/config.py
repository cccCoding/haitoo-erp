from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./haitoro.db"
    secret_key: str = "local-development-secret"
    # 数据库中第三方凭据的加密密钥；未单独配置时兼容既有 SECRET_KEY 密文。
    credential_encryption_key: str | None = None
    access_token_minutes: int = 3 * 24 * 60
    super_admin_access_token_minutes: int = 8 * 60
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    log_level: str = "INFO"
    log_timezone: str = "Asia/Hong_Kong"
    # Grsai 异步图像生成接口，用于印花贴合。
    grsai_base_url: str = "https://grsaiapi.com"
    # DeepSeek 图像理解采用 OpenAI 兼容接口，用于根据模板约束和商品首图生成标题。
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_title_model: str = "deepseek-v4-flash-vision-exp"
    # 新图片统一上传 Cloudflare R2；数据库保存 r2_public_base_url 下的完整 URL。
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    r2_endpoint: str | None = None
    r2_public_base_url: str | None = None
    # true 时将模型的临时结果复制到 R2，避免任务结果依赖第三方 URL 的有效期。
    ai_generated_image_upload_to_r2: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
