"""图片 OCR（可选，扫描页/图表文字）"""

import base64

import httpx

from app.core.settings import settings


async def ocr_image(image_bytes: bytes, *, mime_type: str = "image/png") -> str:
    """DashScope 多模态 OCR；失败时返回空字符串，不阻断解析"""
    # 如果没有配置api key，直接返回空，不发起请求
    if not settings.openai_api_key:
        return ""
    # 图片bytes转base64编码，用于在请求体内联图片
    b64 = base64.b64encode(image_bytes).decode()
    # 拼接请求地址，rstrip('/') 防止出现双斜杠如 https://xxx//chat/completions
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    # 构造多模态请求 payload，兼容OpenAI协议（DashScope兼容OpenAI接口）
    payload = {
        "model": settings.ocr_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                {"type": "text", "text": "请识别图中所有文字，按阅读顺序输出纯文本，不要解释。"},
            ],
        }],
    }
    try:
        # 异步httpx客户端，超时120秒（图片OCR比较慢，超时设的很大）
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            # 取出LLM返回的文本，空兜底+strip
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        # 捕获所有异常：网络超时、接口500、json解析失败、choices不存在等，全部返回空字符串
        return ""
