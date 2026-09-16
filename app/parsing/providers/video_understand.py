import base64
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.core.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VideoUnderstandResult:
    summary: str
    ocr_text: str = ""


def _dashscope_hint(status: int, body: str) -> str:
    hints = [f"HTTP {status}"]
    if body:
        hints.append(body[:200])
    if status == 403:
        hints.append(
            "403 常见原因: ① API Key 无效或未开通 qwen-vl 模型 "
            "② 国内/国际 endpoint 与 Key 不匹配 "
            "（国内: dashscope.aliyuncs.com，国际: dashscope-intl.aliyuncs.com）"
            "③ 账户未开通该模型或余额不足。"
            "开发阶段可设 VIDEO_UNDERSTAND_MOCK=true"
        )
    return " | ".join(hints)


async def describe_frames(frame_paths: list[Path]) -> VideoUnderstandResult:
    """关键帧 → 多模态模型总结"""
    if not frame_paths:
        return VideoUnderstandResult(summary="（无画面帧）")

    if settings.video_understand_mock or not settings.openai_api_key:
        return VideoUnderstandResult(
            summary=f"[mock] 已抽取 {len(frame_paths)} 帧，未调用 VL API（VIDEO_UNDERSTAND_MOCK=true 或未配置 Key）"
        )

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
    try:
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
    except httpx.HTTPStatusError as exc:
        body = exc.response.text
        hint = _dashscope_hint(exc.response.status_code, body)
        logger.warning("视频画面理解 API 失败: %s", hint)
        if settings.video_understand_fail_open:
            return VideoUnderstandResult(summary=f"（画面理解不可用: {hint}）")
        raise ValueError(f"DashScope 视频理解失败: {hint}") from exc
    except Exception as exc:
        logger.warning("视频画面理解异常: %s", exc)
        if settings.video_understand_fail_open:
            return VideoUnderstandResult(summary=f"（画面理解异常: {exc}）")
        raise
