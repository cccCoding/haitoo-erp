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
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    # Grsai 的 Nano Banana 异步图像生成接口，用于印花贴合。
    grsai_api_key: str | None = None
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
    # true 时将 Seedream/千问的临时结果复制到 R2；false 时保留其原始公网 URL。
    # Gemini 只返回内嵌图片，仍必须上传 R2 才能供后续选图和发布使用。
    ai_generated_image_upload_to_r2: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
