import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.settings import settings


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


def probe_media(src: Path) -> MediaProbe:
    cmd = [
        settings.ffprobe_path,
        "-v", "error",
        "-show_entries", "format=duration:stream=codec_type,width,height",
        "-of", "json",
        str(src),
    ]
    import json
    out = subprocess.check_output(cmd, text=True)
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


def split_video_segments(src: Path, out_dir: Path, segment_seconds: int) -> list[VideoSegment]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "seg_%03d.mp4")
    subprocess.run(
        [
            settings.ffmpeg_path, "-y", "-i", str(src),
            "-c", "copy", "-map", "0",
            "-f", "segment", "-segment_time", str(segment_seconds),
            "-reset_timestamps", "1",
            pattern,
        ],
        check=True,
    )
    files = sorted(out_dir.glob("seg_*.mp4"))
    segments: list[VideoSegment] = []
    for i, f in enumerate(files):
        start = i * segment_seconds
        segments.append(VideoSegment(path=f, start_sec=start, end_sec=start + segment_seconds))
    return segments


def extract_audio_wav(video_path: Path, out_wav: Path) -> Path:
    subprocess.run(
        [
            settings.ffmpeg_path, "-y", "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
            str(out_wav),
        ],
        check=True,
    )
    return out_wav


def extract_key_frames(video_path: Path, out_dir: Path, fps: float = 0.2) -> list[Path]:
    """约每 5 秒一帧"""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%04d.jpg")
    subprocess.run(
        [
            settings.ffmpeg_path, "-y", "-i", str(video_path),
            "-vf", f"fps={fps}",
            pattern,
        ],
        check=True,
    )
    return sorted(out_dir.glob("frame_*.jpg"))