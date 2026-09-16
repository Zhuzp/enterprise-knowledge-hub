"""解析 ffmpeg / ffprobe 可执行文件路径（Windows 友好）"""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path

from app.core.settings import settings

_INSTALL_HINT = (
    "视频/音频解析需要 ffmpeg。请任选其一：\n"
    "  1. 安装 ffmpeg 并加入 PATH（Windows: winget install Gyan.FFmpeg）\n"
    "  2. pip install imageio-ffmpeg（自动内置 ffmpeg）\n"
    "  3. 在 .env 中设置 FFMPEG_PATH / FFPROBE_PATH 为完整路径"
)


def _is_executable(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and os.access(p, os.X_OK | os.R_OK)


def _which(name: str) -> str | None:
    found = shutil.which(name)
    if found and _is_executable(found):
        return found
    if os.name == "nt" and not name.lower().endswith(".exe"):
        return _which(f"{name}.exe")
    return None


def _imageio_ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    return exe if exe and _is_executable(exe) else None


def _sibling_ffprobe(ffmpeg_path: str) -> str | None:
    parent = Path(ffmpeg_path).parent
    for name in ("ffprobe", "ffprobe.exe"):
        candidate = parent / name
        if _is_executable(candidate):
            return str(candidate)
    return None


def _windows_common_paths(name: str) -> str | None:
    if os.name != "nt":
        return None
    candidates = [
        Path(r"C:\ffmpeg\bin") / f"{name}.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / f"{name}.exe",
        Path(os.environ.get("ProgramFiles", "")) / "ffmpeg" / "bin" / f"{name}.exe",
    ]
    for p in candidates:
        if p.is_file():
            return str(p)
    return None


@lru_cache(maxsize=1)
def get_ffmpeg_path() -> str:
    configured = settings.ffmpeg_path
    if configured not in ("ffmpeg", "ffprobe") and _is_executable(configured):
        return configured

    for candidate in (
        _which(configured),
        _imageio_ffmpeg(),
        _windows_common_paths("ffmpeg"),
    ):
        if candidate:
            return candidate

    raise FileNotFoundError(_INSTALL_HINT)


@lru_cache(maxsize=1)
def get_ffprobe_path() -> str:
    configured = settings.ffprobe_path
    if configured not in ("ffmpeg", "ffprobe") and _is_executable(configured):
        return configured

    ffmpeg = None
    try:
        ffmpeg = get_ffmpeg_path()
    except FileNotFoundError:
        pass

    for candidate in (
        _which(configured),
        _sibling_ffprobe(ffmpeg) if ffmpeg else None,
        _windows_common_paths("ffprobe"),
    ):
        if candidate:
            return candidate

    # imageio-ffmpeg 不含 ffprobe，由 media.probe_media 走 ffmpeg 降级
    if ffmpeg:
        return ffmpeg

    raise FileNotFoundError(_INSTALL_HINT)
