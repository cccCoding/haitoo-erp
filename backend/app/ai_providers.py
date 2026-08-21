"""印花贴合图像模型适配层。

业务流程只调用 :func:`generate`，每个供应商的鉴权、请求格式和响应格式都由
独立适配器处理。新增豆包、千问等模型时，实现 ``ImageGenerationProvider`` 并
登记到 ``PROVIDERS``，无需修改任务、积分或选图流程。
"""
import base64
import binascii
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

import httpx

from .config import Settings, get_settings


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


class ImageGenerationProvider(Protocol):
    """供应商适配器的稳定边界。返回值一律为系统可访问的图片 URL。"""

    name: str
    credential_env: str

    async def generate(self, request: GenerationRequest, settings: Settings, client: httpx.AsyncClient) -> list[str]: ...


def build_prompt(parameters: dict, template_name: str) -> str:
    placement = parameters["placement"]
    requirement = parameters.get("creative_requirement") or ""
    return (
        f"以产品模板「{template_name}」为主体，将参考印花准确贴合到服装的{placement}区域。"
        "必须保留印花中的文字、Logo、颜色与图案细节，不新增品牌标识；仅自然融合布料的褶皱、光影和遮挡。"
        f"输出电商商品主图，比例 {parameters['ratio']}，清晰度 {parameters['quality']}。{requirement}"
    )


def _public_url(url: str) -> str:
    if url.startswith(("http://", "https://")):
        return url
    base = get_settings().public_media_base_url
    if not base:
        raise ProviderError("未配置 PUBLIC_MEDIA_BASE_URL，模型服务无法读取模板和印花图片")
    return f"{base.rstrip('/')}{url}"


def _urls_from_response(data: dict[str, Any]) -> list[str]:
    candidates = data.get("data") or data.get("output", {}).get("choices") or []
    urls: list[str] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("image_url")
        if isinstance(url, str):
            urls.append(url)
        for content in item.get("message", {}).get("content", []):
            if isinstance(content, dict) and isinstance(content.get("image"), str):
                urls.append(content["image"])
    if not urls:
        raise ProviderError("模型响应中没有可用图片地址")
    return urls


def _save_generated_image(data: bytes, mime_type: str) -> str:
    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime_type, ".png")
    upload_dir = Path(__file__).resolve().parent.parent / "uploads"
    upload_dir.mkdir(exist_ok=True)
    filename = f"generated-{uuid4().hex}{suffix}"
    (upload_dir / filename).write_bytes(data)
    return f"/media/{filename}"


class SeedreamProvider:
    name = "seedream"
    credential_env = "SEEDREAM_API_KEY"

    async def generate(self, request: GenerationRequest, settings: Settings, client: httpx.AsyncClient) -> list[str]:
        if not settings.seedream_api_key:
            raise ProviderError(f"未配置 {self.credential_env}")
        images = [_public_url(request.template_url), *[_public_url(url) for url in request.print_urls]]
        response = await client.post(
            f"{settings.seedream_base_url.rstrip('/')}/images/generations",
            headers={"Authorization": f"Bearer {settings.seedream_api_key}"},
            json={"model": request.model, "prompt": request.prompt, "image": images, "size": "2048x2048" if request.quality == "2K" else "1024x1024", "response_format": "url", "n": 2},
        )
        _raise_for_provider_error(self.name, response)
        return _urls_from_response(response.json())


class QwenProvider:
    name = "qwen"
    credential_env = "QWEN_API_KEY"

    async def generate(self, request: GenerationRequest, settings: Settings, client: httpx.AsyncClient) -> list[str]:
        if not settings.qwen_api_key:
            raise ProviderError(f"未配置 {self.credential_env}")
        images = [_public_url(request.template_url), *[_public_url(url) for url in request.print_urls]]
        content = [{"image": image} for image in images] + [{"text": request.prompt}]
        response = await client.post(
            settings.qwen_base_url,
            headers={"Authorization": f"Bearer {settings.qwen_api_key}", "X-DashScope-Async": "enable"},
            json={"model": request.model, "input": {"messages": [{"role": "user", "content": content}]}, "parameters": {"n": 2, "size": "2048*2048" if request.quality == "2K" else "1024*1024"}},
        )
        _raise_for_provider_error(self.name, response)
        return _urls_from_response(response.json())


class GeminiProvider:
    """Gemini 2.5 Flash Image 适配器。

    Gemini 的 generateContent 接口要求输入图片以 inlineData/fileData 提交，且将生成
    图片作为 inlineData 返回；这里下载公开参考图、转为 base64，并把结果保存到
    本地媒体目录，以保持业务层始终使用 URL 的约定。
    """

    name = "gemini"
    credential_env = "GEMINI_API_KEY"

    async def generate(self, request: GenerationRequest, settings: Settings, client: httpx.AsyncClient) -> list[str]:
        if not settings.gemini_api_key:
            raise ProviderError(f"未配置 {self.credential_env}")
        source_urls = [_public_url(request.template_url), *[_public_url(url) for url in request.print_urls]]
        image_parts = [await self._input_image_part(url, client) for url in source_urls]
        response = await client.post(
            f"{settings.gemini_base_url.rstrip('/')}/models/{request.model}:generateContent",
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"role": "user", "parts": [{"text": request.prompt}, *image_parts]}],
                "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
            },
        )
        _raise_for_provider_error(self.name, response)
        return self._generated_image_urls(response.json())

    async def _input_image_part(self, url: str, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.get(url)
        _raise_for_provider_error(self.name, response)
        mime_type = response.headers.get("content-type", "image/png").split(";", 1)[0].lower()
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ProviderError(f"Gemini 不支持参考图格式：{mime_type}")
        if len(response.content) > 20 * 1024 * 1024:
            raise ProviderError("参考图超过 Gemini 允许的 20MB 上限")
        return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(response.content).decode("ascii")}}

    def _generated_image_urls(self, data: dict[str, Any]) -> list[str]:
        urls: list[str] = []
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if not isinstance(inline_data, dict) or not isinstance(inline_data.get("data"), str):
                    continue
                try:
                    urls.append(_save_generated_image(base64.b64decode(inline_data["data"]), inline_data.get("mimeType", "image/png")))
                except (ValueError, binascii.Error) as exc:
                    raise ProviderError("Gemini 返回了无效的图片数据") from exc
        if not urls:
            raise ProviderError("Gemini 响应中没有可用图片")
        return urls


def _raise_for_provider_error(provider: str, response: httpx.Response) -> None:
    if response.is_error:
        raise ProviderError(f"{provider} 调用失败：{response.status_code} {response.text[:300]}")


PROVIDERS: dict[str, ImageGenerationProvider] = {
    SeedreamProvider.name: SeedreamProvider(),
    QwenProvider.name: QwenProvider(),
    GeminiProvider.name: GeminiProvider(),
}


def provider_credential_env(provider: str) -> str | None:
    adapter = PROVIDERS.get(provider)
    return adapter.credential_env if adapter else None


async def generate(provider: str, request: GenerationRequest) -> list[str]:
    adapter = PROVIDERS.get(provider)
    if not adapter:
        raise ProviderError("不支持的模型提供方")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.generate(request, get_settings(), client)
