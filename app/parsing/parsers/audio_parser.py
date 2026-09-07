from app.parsing.parsers.base import BaseParser
from app.parsing.providers.asr import transcribe_bytes
from app.parsing.schemas import ParseResult


class AudioParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        if progress_callback:
            await progress_callback(0.1, "asr start")

        asr = await transcribe_bytes(file_data, file_name)

        if progress_callback:
            await progress_callback(1.0, "asr done")

        md = (
            f"# {file_name}\n\n"
            f"- 类型: audio\n"
            f"- 时长: {asr.duration_sec:.1f}s\n\n"
            f"## 转写文本\n\n{asr.text or '（未识别到语音）'}\n"
        )
        if asr.segments:
            md += "\n## 时间轴\n"
            for seg in asr.segments:
                md += f"\n### [{seg.start:.1f}s - {seg.end:.1f}s]\n{seg.text}\n"

        return ParseResult(
            markdown=md,
            metadata={"parser": "audio", "duration_sec": asr.duration_sec},
        )