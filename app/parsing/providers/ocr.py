"""图片 OCR（可选，扫描页/图表文字）"""

import base64

import httpx

from app.core.settings import settings


async def ocr_image(image_bytes: bytes) -> str:
    """DashScope 多模态 OCR；失败时返回空字符串，不阻断解析"""
    if not settings.openai_api_key:
        return ""

    b64 = base64.b64encode(image_bytes).decode()
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.ocr_model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                {"type": "text", "text": "请识别图中所有文字，按阅读顺序输出纯文本，不要解释。"},
            ],
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            return (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except Exception:
        return ""
