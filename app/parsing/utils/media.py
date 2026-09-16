import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.parsing.utils.ffmpeg_bin import get_ffmpeg_path, get_ffprobe_path

# Windows 默认 gbk 解码 ffmpeg stderr 会报错
_SUBPROCESS_TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


@dataclass
class VideoSegment:
    path: Path
    start_sec: float
    end_sec: float
    text: str = ""   # ASR 结果填这里


@dataclass
class MediaProbe:
    duration_sec: float
    has_audio: bool
    width: int = 0
    height: int = 0


def _run_ffmpeg(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, **_SUBPROCESS_TEXT)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            "找不到 ffmpeg/ffprobe 可执行文件。"
            "Windows 可执行: winget install Gyan.FFmpeg，或 pip install imageio-ffmpeg"
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if "Invalid data" in stderr or "moov atom not found" in stderr:
            raise ValueError(
                "视频文件无效或损坏（可能是占位 MP4）。"
                "请用 ffmpeg 生成真实视频，或上传其他格式测试。"
            ) from exc
        raise ValueError(f"ffmpeg 处理失败: {stderr.strip()[:300]}") from exc


def _probe_with_ffprobe(src: Path) -> MediaProbe:
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json",
        str(src),
    ]
    # ffprobe 与 ffmpeg 同名时（imageio 降级）走 stderr 解析
    if Path(ffprobe).name.lower().startswith("ffmpeg"):
        return _probe_with_ffmpeg_stderr(src)

    out = subprocess.check_output(cmd, **_SUBPROCESS_TEXT)
    data = json.loads(out)
    duration = float(data.get("format", {}).get("duration") or 0)
    streams = data.get("streams") or []
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    return MediaProbe(
        duration_sec=duration,
        has_audio=has_audio,
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
    )


def _probe_with_ffmpeg_stderr(src: Path) -> MediaProbe:
    ffmpeg = get_ffmpeg_path()
    cmd = [ffmpeg, "-i", str(src), "-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, **_SUBPROCESS_TEXT)
    stderr = result.stderr or ""

    if "Invalid data" in stderr or "moov atom not found" in stderr:
        raise ValueError(
            "视频文件无效或损坏（可能是占位 MP4）。"
            "请运行: python scripts/generate_test_fixtures.py（需 ffmpeg）"
        )

    duration = 0.0
    m = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", stderr)
    if m:
        h, mi, s = m.groups()
        duration = int(h) * 3600 + int(mi) * 60 + float(s)

    has_audio = "Audio:" in stderr
    width = height = 0
    vm = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr)
    if vm:
        width, height = int(vm.group(1)), int(vm.group(2))

    if duration <= 0:
        raise ValueError(f"无法读取视频时长，请确认文件完整: {src.name}")

    return MediaProbe(duration_sec=duration, has_audio=has_audio, width=width, height=height)


def probe_media(src: Path) -> MediaProbe:
    try:
        return _probe_with_ffprobe(src)
    except FileNotFoundError:
        raise
    except (json.JSONDecodeError, subprocess.CalledProcessError, KeyError):
        return _probe_with_ffmpeg_stderr(src)


def split_video_segments(src: Path, out_dir: Path, segment_seconds: int) -> list[VideoSegment]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "seg_%03d.mp4")
    _run_ffmpeg([
        get_ffmpeg_path(), "-y", "-i", str(src),
        "-c", "copy", "-map", "0",
        "-f", "segment", "-segment_time", str(segment_seconds),
        "-reset_timestamps", "1",
        pattern,
    ])
    files = sorted(out_dir.glob("seg_*.mp4"))
    if not files:
        raise ValueError("视频分片失败，未生成任何 segment 文件")
    segments: list[VideoSegment] = []
    for i, f in enumerate(files):
        start = i * segment_seconds
        segments.append(VideoSegment(path=f, start_sec=start, end_sec=start + segment_seconds))
    return segments


def extract_audio_wav(video_path: Path, out_wav: Path) -> Path:
    _run_ffmpeg([
        get_ffmpeg_path(), "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(out_wav),
    ])
    return out_wav


def extract_key_frames(video_path: Path, out_dir: Path, fps: float = 0.2) -> list[Path]:
    """约每 5 秒一帧"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%04d.jpg")
    _run_ffmpeg([
        get_ffmpeg_path(), "-y", "-i", str(video_path),
        "-vf", f"fps={fps}",
        pattern,
    ])
    frames = sorted(out_dir.glob("frame_*.jpg"))
    if not frames:
        raise ValueError("未能从视频中抽取关键帧")
    return frames
