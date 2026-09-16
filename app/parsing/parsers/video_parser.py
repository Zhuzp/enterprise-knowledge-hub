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

        # 创建临时目录，所有视频切片、帧图片、wav音频都放这里
        # with自动管理：代码块结束后自动删除临时目录，清理磁盘文件
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 在临时目录写入原始视频文件（把二进制file_data落地到临时文件）
            src = tmp_path / file_name
            src.write_bytes(file_data)

            # 使用ffmpeg探测视频时长、分辨率等元信息
            probe = probe_media(src)
            #校验视频总时长，如果超过配置上限，直接抛异常拒绝解析
            if probe.duration_sec > settings.video_max_duration_seconds:
                raise ValueError(
                    f"视频过长({probe.duration_sec:.0f}s)，上限 {settings.video_max_duration_seconds}s"
                )

            # Markdown写入视频总时长信息
            md_parts.append(f"- 时长: {probe.duration_sec:.1f}s\n")

            # 将完整视频切分成多个小段，每段长度由配置video_segment_seconds决定
            # 分片目的：长视频不能一次性丢给VL/ASR；分段处理降低单任务负载、方便分片RAG
            segments = split_video_segments(
                src, tmp_path / "segments", settings.video_segment_seconds
            )
            total = max(len(segments), 1)

            # 循环处理每一个视频分片
            for i, seg in enumerate(segments, start=1):
                # 进度回调，上报当前处理分片序号，用于前端进度展示
                if progress_callback:
                    await progress_callback(
                        (i - 1) / total,
                        f"segment {i}/{total}",
                    )
                # Markdown二级标题：标记当前分片的起止时间
                md_parts.append(f"\n## Segment {i} ({seg.start_sec:.0f}s - {seg.end_sec:.0f}s)\n")

                # ===== 1.画面理解：提取关键帧，调用多模态模型看懂画面 =====
                # 从当前视频分片提取关键帧图片，保存到临时目录
                frames = extract_key_frames(seg.path, tmp_path / f"frames_{i:03d}")
                # 调用VL多模态接口，传入帧图片，生成画面摘要
                visual = await describe_frames(frames)
                md_parts.append(f"### 画面理解\n{visual.summary}\n")

                # ===== 2.语音ASR转写：提取音频，转文字 =====
                if probe.has_audio:
                    # 从当前分片提取音频，输出wav格式
                    wav = tmp_path / f"seg_{i:03d}.wav"
                    extract_audio_wav(seg.path, wav)
                    # ASR语音转写，得到文本
                    asr = await transcribe_file(str(wav), f"seg_{i}.wav")
                    seg.text = asr.text
                    # 写入markdown语音文本
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