"""ffmpeg 路径解析"""

from app.parsing.utils.ffmpeg_bin import get_ffmpeg_path


def test_get_ffmpeg_path_resolves():
    path = get_ffmpeg_path()
    assert path
    assert "ffmpeg" in path.lower()
