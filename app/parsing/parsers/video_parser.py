import tempfile
from pathlib import Path

from app.core.settings import settings
from app.parsing.parsers.base import BaseParser
from app.parsing.providers.asr import transcribe_file
from app.parsing.providers.video_understand import describe_frames
from app.parsing.schemas import ParseResult
from app.parsing.utils.media import (
    extract_audio_wav,
    extract_key_frames,
    probe_media,
    split_video_segments,
)


class VideoParser(BaseParser):
    async def parse(self, *, file_data, file_name, owner_id, doc_uuid, progress_callback=None):
        md_parts = [f"# {file_name}\n", f"- 类型: video\n"]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / file_name
            src.write_bytes(file_data)

            probe = probe_media(src)
            if probe.duration_sec > settings.video_max_duration_seconds:
                raise ValueError(
                    f"视频过长({probe.duration_sec:.0f}s)，上限 {settings.video_max_duration_seconds}s"
                )

            md_parts.append(f"- 时长: {probe.duration_sec:.1f}s\n")

            segments = split_video_segments(
                src, tmp_path / "segments", settings.video_segment_seconds
            )
            total = max(len(segments), 1)

            for i, seg in enumerate(segments, start=1):
                if progress_callback:
                    await progress_callback(
                        (i - 1) / total,
                        f"segment {i}/{total}",
                    )

                md_parts.append(f"\n## Segment {i} ({seg.start_sec:.0f}s - {seg.end_sec:.0f}s)\n")

                # 1) 画面理解
                frames = extract_key_frames(seg.path, tmp_path / f"frames_{i:03d}")
                visual = await describe_frames(frames)
                md_parts.append(f"### 画面理解\n{visual.summary}\n")

                # 2) 音轨 ASR
                if probe.has_audio:
                    wav = tmp_path / f"seg_{i:03d}.wav"
                    extract_audio_wav(seg.path, wav)
                    asr = await transcribe_file(str(wav), f"seg_{i}.wav")
                    seg.text = asr.text
                    md_parts.append(f"### 语音转写\n{asr.text or '（无语音）'}\n")
                else:
                    md_parts.append("### 语音转写\n（无音轨）\n")

            if progress_callback:
                await progress_callback(1.0, "done")

        return ParseResult(
            markdown="\n".join(md_parts),
            metadata={
                "parser": "video",
                "duration_sec": probe.duration_sec,
                "segment_count": len(segments),
            },
        )