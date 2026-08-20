from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./haitoo.db"
    secret_key: str = "local-development-secret"
    access_token_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://localhost:5174"
    # 密钥只从环境变量读取，绝不保存到数据库或返回给前端。
    seedream_api_key: str | None = None
    seedream_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    public_media_base_url: str | None = None
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
