from functools import lru_cache
from typing import Literal
from pydantic import Field, model_validator
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
    # 仅本机代理兼容：允许图片域名解析到 Fake-IP 保留网段，生产环境保持关闭。
    image_download_allow_fake_ip: bool = False
    # auto 仅在请求来自内部代理时读取 Cloudflare / Nginx 覆写的客户端 IP 头。
    login_client_ip_source: Literal["peer", "auto"] = "peer"
    # Grsai 异步图像生成接口，用于印花贴合。
    grsai_base_url: str = "https://grsaiapi.com"
    # DeepSeek 英文标题采用 OpenAI 兼容接口，密钥按当前用户从数据库读取。
    deepseek_base_url: str = "https://api.deepseek.com"
    supply_worker_concurrency: int = Field(default=4, gt=0)
    supply_company_concurrency: int = Field(default=2, gt=0)
    supply_title_concurrency: int = Field(default=3, gt=0)
    supply_heartbeat_seconds: int = Field(default=15, gt=0)
    supply_lease_seconds: int = Field(default=90, gt=0)
    supply_file_retention_days: int = Field(default=7, gt=0)

    @model_validator(mode="after")
    def validate_supply_lease(self):
        if self.supply_heartbeat_seconds >= self.supply_lease_seconds:
            raise ValueError("货盘续租间隔必须小于租约有效时间")
        return self
    # 新图片统一上传 Cloudflare R2；数据库保存 r2_public_base_url 下的完整 URL。
    r2_account_id: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_bucket: str | None = None
    r2_hub_export_bucket: str | None = None
    r2_endpoint: str | None = None
    r2_public_base_url: str | None = None
    # true 时将模型的临时结果复制到 R2，避免任务结果依赖第三方 URL 的有效期。
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
