"""印花贴合图像模型适配层。

业务流程只调用 :func:`generate`，每个供应商的鉴权、请求格式和响应格式都由
Grsai 的模型差异集中在本模块，任务与选图流程只处理统一的异步任务协议。
"""
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings, get_settings
from .storage import is_public_r2_url


logger = logging.getLogger(__name__)


class ProviderError(Exception):
    pass


class ProviderTaskTerminalError(ProviderError):
    """外部异步任务已明确结束且失败，不应作为查询故障自动重新提交。"""


@dataclass
class GenerationRequest:
    model: str
    prompt: str
    template_url: str
    print_urls: list[str]
    ratio: str
    quality: str
    company_id: int
    task_id: int
    idempotency_key: str


def build_prompt(parameters: dict, template_name: str) -> str:
    requirement = parameters.get("creative_requirement") or ""
    output_name = {
        "carousel": "电商商品轮播图",
        "main_image": "电商商品首图",
    }.get(parameters.get("task_type"), "带指定印花的 SKU 商品图")
    return (
        f"{requirement}。输出{output_name}，比例 {parameters['ratio']}，清晰度 {parameters['quality']}。"
    )


def _public_url(url: str) -> str:
    if is_public_r2_url(url):
        return url
    raise ProviderError("图片未上传至当前 Cloudflare R2 公网域名，无法提交给模型服务")


class GrsaiProvider:
    """Grsai Nano Banana 异步图像生成适配器。"""

    name = "grsai"
    async def submit(self, request: GenerationRequest, api_key: str, settings: Settings, client: httpx.AsyncClient) -> tuple[dict[str, Any], str, dict[str, str]]:
        images = [_public_url(request.template_url), *[_public_url(url) for url in request.print_urls]]
        base_url = settings.grsai_base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}", "Idempotency-Key": request.idempotency_key}
        payload: dict[str, Any] = {
            "model": request.model,
            "prompt": request.prompt,
            "images": images,
            "aspectRatio": request.ratio,
            "replyType": "async",
        }
        if request.model == "gpt-image-2":
            payload["quality"] = "auto"
        else:
            payload["imageSize"] = request.quality
        response = await client.post(
            f"{base_url}/v1/api/generate",
            headers=headers,
            json=payload,
        )
        _raise_for_provider_error(self.name, response)
        return self._response_data(response), base_url, headers

    @staticmethod
    def _response_data(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "grsai 响应 JSON 解析失败 | status_code=%s content_type=%s raw_body=%r",
                response.status_code,
                response.headers.get("content-type"),
                response.text,
            )
            raise ProviderError("grsai 返回了无效的 JSON 响应") from exc
        if not isinstance(data, dict):
            raise ProviderError("grsai 返回了无效的响应格式")
        return data

    async def poll_once(self, provider_task_id: str, api_key: str, settings: Settings, client: httpx.AsyncClient) -> list[str] | None:
        """只查询一次外部任务；未完成返回 None，不占用 worker 等待。"""
        response = await client.get(
            f"{settings.grsai_base_url.rstrip('/')}/v1/api/result",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"id": provider_task_id},
        )
        _raise_for_provider_error(self.name, response)
        result = self._response_data(response)
        status = str(result.get("status", "")).lower()
        if status == "succeeded":
            urls = [item["url"] for item in result.get("results", []) if isinstance(item, dict) and isinstance(item.get("url"), str)]
            if not urls:
                raise ProviderError("grsai 任务成功但未返回图片地址")
            return urls
        if status in {"failed", "violation"}:
            raise ProviderTaskTerminalError(f"grsai 任务{status}：{result.get('error') or '未提供原因'}")
        return None


def _raise_for_provider_error(provider: str, response: httpx.Response) -> None:
    if response.is_error:
        raise ProviderError(f"{provider} 调用失败：{response.status_code} {response.text[:300]}")


GRSAI_PROVIDER_KEYS = {"grsai", "grsai-gpt-image-2"}
PROVIDERS: dict[str, GrsaiProvider] = {key: GrsaiProvider() for key in GRSAI_PROVIDER_KEYS}


def provider_supports_user_credentials(provider: str) -> bool:
    return provider in PROVIDERS


async def submit_async_generation(provider: str, request: GenerationRequest, api_key: str) -> tuple[dict[str, Any], str, dict[str, str]]:
    """提交支持外部异步任务的模型，并返回供应商响应和查询所需上下文。"""
    adapter = PROVIDERS.get(provider)
    if provider not in GRSAI_PROVIDER_KEYS or not isinstance(adapter, GrsaiProvider):
        raise ProviderError("当前模型不支持异步任务提交")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.submit(request, api_key, get_settings(), client)


async def poll_async_generation(provider: str, provider_task_id: str, api_key: str) -> list[str] | None:
    adapter = PROVIDERS.get(provider)
    if provider not in GRSAI_PROVIDER_KEYS or not isinstance(adapter, GrsaiProvider):
        raise ProviderError("当前模型不支持异步任务查询")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.poll_once(provider_task_id, api_key, get_settings(), client)


async def generate_draft_title(title_constraint: str, image_url: str) -> str:
    """使用 DeepSeek 视觉模型根据模板标题约束和商品首图生成标题。"""
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ProviderError("未配置 DEEPSEEK_API_KEY")
    image_reference = _public_url(image_url)
    prompt = (
        "你是跨境电商商品标题助手。请识别商品首图中的商品、款式、颜色、材质、图案和可见细节，"
        "并严格遵守以下标题约束生成一个中文商品标题。"
        "只输出标题本身，不要解释、不要引号、不要 Markdown；标题长度必须为 25-255 个字符。\n"
        f"标题约束：{title_constraint}"
    )
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_title_model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_reference}, "detail": "high"},
                    ],
                }],
                "temperature": 0.4,
                "max_tokens": 240,
            },
        )
    _raise_for_provider_error("deepseek", response)
    title = str(response.json().get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
    if not title:
        raise ProviderError("DeepSeek 未返回标题")
    if len(title) < 25:
        raise ProviderError("DeepSeek 返回的标题少于 25 个字符，请重试或手动填写")
    return title[:255]
