import asyncio
from dataclasses import dataclass, field

import httpx

from app.core.settings import settings


@dataclass
class AsrSegment:
    start: float
    end: float
    text: str


@dataclass
class AsrResult:
    text: str
    duration_sec: float = 0.0
    segments: list[AsrSegment] = field(default_factory=list)


async def transcribe_file(file_path: str, file_name: str) -> AsrResult:
    """
    DashScope Paraformer 文件转写（示意）
    生产：先 upload file → 拿 file_id → 提交 transcription job → 轮询
    """
    def _call():
        # TODO: 按 DashScope 文档接真实 API
        # 开发阶段可 mock：
        return AsrResult(text=f"[ASR mock] {file_name}", duration_sec=0.0)

    return await asyncio.to_thread(_call)


async def transcribe_bytes(file_data: bytes, file_name: str) -> AsrResult:
    import tempfile
    from pathlib import Path

    suffix = Path(file_name).suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_data)
        tmp = f.name
    try:
        return await transcribe_file(tmp, file_name)
    finally:
        Path(tmp).unlink(missing_ok=True)