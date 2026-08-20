"""印花贴合模型适配层。

每个提供方在这里隔离；任务创建与积分逻辑不依赖供应商。两家服务均使用其
图像编辑接口，并把模板图、印花图作为参考图传入。生产环境的图片 URL 必须能
被模型服务访问，因此请配置 PUBLIC_MEDIA_BASE_URL 为公开 HTTPS 地址。
"""
from dataclasses import dataclass
from typing import Any
import httpx

from .config import get_settings


class ProviderError(Exception):
    pass


@dataclass
class GenerationRequest:
    model: str
    prompt: str
    template_url: str
    print_urls: list[str]
    ratio: str
    quality: str


def build_prompt(parameters: dict, template_name: str) -> str:
    placement = parameters["placement"]
    requirement = parameters.get("creative_requirement") or ""
    return (
        f"以产品模板「{template_name}」为主体，将参考印花准确贴合到服装的{placement}区域。"
        "必须保留印花中的文字、Logo、颜色与图案细节，不新增品牌标识；仅自然融合布料的褶皱、光影和遮挡。"
        f"输出电商商品主图，比例 {parameters['ratio']}，清晰度 {parameters['quality']}。{requirement}"
    )


def _public_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    base = get_settings().public_media_base_url
    if not base:
        raise ProviderError("未配置 PUBLIC_MEDIA_BASE_URL，模型服务无法读取模板和印花图片")
    return f"{base.rstrip('/')}{url}"


def _urls_from_response(data: dict[str, Any]) -> list[str]:
    candidates = data.get("data") or data.get("output", {}).get("choices") or []
    urls: list[str] = []
    for item in candidates:
        if isinstance(item, dict):
            url = item.get("url") or item.get("image_url")
            if isinstance(url, str):
                urls.append(url)
            for content in item.get("message", {}).get("content", []):
                if isinstance(content, dict) and isinstance(content.get("image"), str):
                    urls.append(content["image"])
    if not urls:
        raise ProviderError("模型响应中没有可用图片地址")
    return urls


async def generate(provider: str, request: GenerationRequest) -> list[str]:
    settings = get_settings()
    images = [_public_url(request.template_url), *[_public_url(url) for url in request.print_urls]]
    async with httpx.AsyncClient(timeout=120) as client:
        if provider == "seedream":
            if not settings.seedream_api_key:
                raise ProviderError("未配置 SEEDREAM_API_KEY")
            response = await client.post(
                f"{settings.seedream_base_url.rstrip('/')}/images/generations",
                headers={"Authorization": f"Bearer {settings.seedream_api_key}"},
                json={"model": request.model, "prompt": request.prompt, "image": images, "size": "2048x2048" if request.quality == "2K" else "1024x1024", "response_format": "url", "n": 2},
            )
        elif provider == "qwen":
            if not settings.qwen_api_key:
                raise ProviderError("未配置 QWEN_API_KEY")
            content = [{"image": image} for image in images] + [{"text": request.prompt}]
            response = await client.post(
                settings.qwen_base_url,
                headers={"Authorization": f"Bearer {settings.qwen_api_key}", "X-DashScope-Async": "enable"},
                json={"model": request.model, "input": {"messages": [{"role": "user", "content": content}]}, "parameters": {"n": 2, "size": "2048*2048" if request.quality == "2K" else "1024*1024"}},
            )
        else:
            raise ProviderError("不支持的模型提供方")
        if response.is_error:
            raise ProviderError(f"{provider} 调用失败：{response.status_code} {response.text[:300]}")
        return _urls_from_response(response.json())
