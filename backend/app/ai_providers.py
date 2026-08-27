"""印花贴合图像模型适配层。

业务流程只调用 :func:`generate`，每个供应商的鉴权、请求格式和响应格式都由
独立适配器处理。新增豆包、千问等模型时，实现 ``ImageGenerationProvider`` 并
登记到 ``PROVIDERS``，无需修改任务、积分或选图流程。
"""
import asyncio
import base64
import binascii
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from .config import Settings, get_settings
from .storage import StorageError, is_public_r2_url, upload_image_bytes_async


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
    company_id: int
    task_id: int


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
    if is_public_r2_url(url):
        return url
    raise ProviderError("图片未上传至当前 Cloudflare R2 公网域名，无法提交给模型服务")


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


async def _save_generated_image(data: bytes, mime_type: str, company_id: int, task_id: int) -> str:
    try:
        return await upload_image_bytes_async(data, mime_type, company_id, f"generated/task-{task_id}")
    except StorageError as exc:
        raise ProviderError(str(exc)) from exc


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
    图片作为 inlineData 返回；这里下载公开参考图、转为 base64，并将结果上传
    Cloudflare R2，以保持业务层始终使用稳定公网 URL 的约定。
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
        return await self._generated_image_urls(response.json(), request.company_id, request.task_id)

    async def _input_image_part(self, url: str, client: httpx.AsyncClient) -> dict[str, Any]:
        response = await client.get(url)
        _raise_for_provider_error(self.name, response)
        mime_type = response.headers.get("content-type", "image/png").split(";", 1)[0].lower()
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ProviderError(f"Gemini 不支持参考图格式：{mime_type}")
        if len(response.content) > 20 * 1024 * 1024:
            raise ProviderError("参考图超过 Gemini 允许的 20MB 上限")
        return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(response.content).decode("ascii")}}

    async def _generated_image_urls(self, data: dict[str, Any], company_id: int, task_id: int) -> list[str]:
        urls: list[str] = []
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if not isinstance(inline_data, dict) or not isinstance(inline_data.get("data"), str):
                    continue
                try:
                    urls.append(await _save_generated_image(base64.b64decode(inline_data["data"]), inline_data.get("mimeType", "image/png"), company_id, task_id))
                except (ValueError, binascii.Error) as exc:
                    raise ProviderError("Gemini 返回了无效的图片数据") from exc
        if not urls:
            raise ProviderError("Gemini 响应中没有可用图片")
        return urls


class GrsaiProvider:
    """Grsai Nano Banana 异步图像生成适配器。"""

    name = "grsai"
    credential_env = "GRSAI_API_KEY"
    # 供应商任务可能持续较长时间；降低查询频率以避免无意义的外部请求。
    _poll_interval_seconds = 5 * 60
    _max_poll_attempts = 144

    async def generate(self, request: GenerationRequest, settings: Settings, client: httpx.AsyncClient) -> list[str]:
        result, base_url, headers = await self.submit(request, settings, client)
        return await self.wait_for_result(result, base_url, headers, client)

    async def submit(self, request: GenerationRequest, settings: Settings, client: httpx.AsyncClient) -> tuple[dict[str, Any], str, dict[str, str]]:
        if not settings.grsai_api_key:
            raise ProviderError(f"未配置 {self.credential_env}")
        images = [_public_url(request.template_url), *[_public_url(url) for url in request.print_urls]]
        base_url = settings.grsai_base_url.rstrip("/")
        headers = {"Authorization": f"Bearer {settings.grsai_api_key}"}
        response = await client.post(
            f"{base_url}/v1/api/generate",
            headers=headers,
            json={
                "model": request.model,
                "prompt": request.prompt,
                "images": images,
                "aspectRatio": request.ratio,
                "imageSize": request.quality,
                "replyType": "async",
            },
        )
        _raise_for_provider_error(self.name, response)
        return self._response_data(response), base_url, headers

    @staticmethod
    def _response_data(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("grsai 返回了无效的 JSON 响应") from exc
        if not isinstance(data, dict):
            raise ProviderError("grsai 返回了无效的响应格式")
        return data

    async def wait_for_result(self, result: dict[str, Any], base_url: str, headers: dict[str, str], client: httpx.AsyncClient) -> list[str]:
        for _ in range(self._max_poll_attempts):
            status = str(result.get("status", "")).lower()
            if status == "succeeded":
                urls = [item["url"] for item in result.get("results", []) if isinstance(item, dict) and isinstance(item.get("url"), str)]
                if urls:
                    return urls
                raise ProviderError("grsai 任务成功但未返回图片地址")
            if status in {"failed", "violation"}:
                raise ProviderError(f"grsai 任务{status}：{result.get('error') or '未提供原因'}")
            task_id = result.get("id")
            if not isinstance(task_id, str) or not task_id:
                raise ProviderError("grsai 异步任务未返回任务 ID")
            await asyncio.sleep(self._poll_interval_seconds)
            response = await client.get(f"{base_url}/v1/api/result", headers=headers, params={"id": task_id})
            _raise_for_provider_error(self.name, response)
            result = self._response_data(response)
        raise ProviderError("grsai 任务查询超时，请稍后重试")


def _raise_for_provider_error(provider: str, response: httpx.Response) -> None:
    if response.is_error:
        raise ProviderError(f"{provider} 调用失败：{response.status_code} {response.text[:300]}")


PROVIDERS: dict[str, ImageGenerationProvider] = {
    SeedreamProvider.name: SeedreamProvider(),
    QwenProvider.name: QwenProvider(),
    GeminiProvider.name: GeminiProvider(),
    GrsaiProvider.name: GrsaiProvider(),
}


def provider_credential_env(provider: str) -> str | None:
    adapter = PROVIDERS.get(provider)
    return adapter.credential_env if adapter else None


def provider_has_credentials(provider: str) -> bool:
    """判断模型必要的 API 密钥是否已由部署环境注入。"""
    credential_env = provider_credential_env(provider)
    if not credential_env:
        return False
    return bool(getattr(get_settings(), credential_env.lower()))


async def generate(provider: str, request: GenerationRequest) -> list[str]:
    adapter = PROVIDERS.get(provider)
    if not adapter:
        raise ProviderError("不支持的模型提供方")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.generate(request, get_settings(), client)


async def submit_async_generation(provider: str, request: GenerationRequest) -> tuple[dict[str, Any], str, dict[str, str]]:
    """提交支持外部异步任务的模型，并返回供应商响应和查询所需上下文。"""
    adapter = PROVIDERS.get(provider)
    if not isinstance(adapter, GrsaiProvider):
        raise ProviderError("当前模型不支持异步任务提交")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.submit(request, get_settings(), client)


async def wait_for_async_generation(provider: str, initial_result: dict[str, Any], base_url: str, headers: dict[str, str]) -> list[str]:
    """根据供应商异步任务 ID 轮询并取得最终图片地址。"""
    adapter = PROVIDERS.get(provider)
    if not isinstance(adapter, GrsaiProvider):
        raise ProviderError("当前模型不支持异步任务查询")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.wait_for_result(initial_result, base_url, headers, client)


async def resume_async_generation(provider: str, provider_task_id: str) -> list[str]:
    """重新查询一个已提交的供应商异步任务，不会重新发起图片生成。"""
    adapter = PROVIDERS.get(provider)
    if not isinstance(adapter, GrsaiProvider):
        raise ProviderError("当前模型不支持异步任务查询")
    settings = get_settings()
    if not settings.grsai_api_key:
        raise ProviderError(f"未配置 {adapter.credential_env}")
    async with httpx.AsyncClient(timeout=120) as client:
        return await adapter.wait_for_result(
            {"id": provider_task_id, "status": "running"},
            settings.grsai_base_url.rstrip("/"),
            {"Authorization": f"Bearer {settings.grsai_api_key}"},
            client,
        )


async def generate_draft_title(title_constraint: str, image_url: str) -> str:
    """使用 DeepSeek 视觉模型根据模板标题约束和商品首图生成标题。"""
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise ProviderError("未配置 DEEPSEEK_API_KEY")
    image_reference = _public_url(image_url)
    prompt = (
        "你是跨境电商商品标题助手。请识别商品首图中的商品、款式、颜色、材质、图案和可见细节，"
        "并严格遵守以下标题约束生成一个中文商品标题。"
        "只输出标题本身，不要解释、不要引号、不要 Markdown；标题不超过 180 个字符。\n"
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
    return title[:180]
