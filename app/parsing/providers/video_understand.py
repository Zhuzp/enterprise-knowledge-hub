import base64
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.settings import settings


@dataclass
class VideoUnderstandResult:
    summary: str
    ocr_text: str = ""


async def describe_frames(frame_paths: list[Path]) -> VideoUnderstandResult:
    """关键帧 → 多模态模型总结"""
    if not frame_paths:
        return VideoUnderstandResult(summary="（无画面帧）")

    # 取前 3 帧，避免 token 爆炸
    contents = []
    for p in frame_paths[:3]:
        b64 = base64.b64encode(p.read_bytes()).decode()
        contents.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })
    contents.append({
        "type": "text",
        "text": "请用中文总结这段视频画面的主要内容、可见文字和关键动作，不要编造。",
    })

    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.video_model,
                "messages": [{"role": "user", "content": contents}],
            },
        )
        resp.raise_for_status()
        summary = resp.json()["choices"][0]["message"]["content"]
    return VideoUnderstandResult(summary=summary)