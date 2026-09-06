from app.core.settings import settings


def split_text(text: str) -> list[str]:
    """把长文本切成多个 chunk"""
    chunk_size = settings.chunk_size
    overlap = settings.chunk_overlap
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # 尽量在句号/换行处切断，避免截断句子
        if end < len(text):
            for sep in ["\n\n", "\n", "。", "."]:
                last_sep = chunk.rfind(sep)
                if last_sep > chunk_size // 2:
                    chunk = chunk[: last_sep + len(sep)]
                    end = start + len(chunk)
                    break

        chunks.append(chunk.strip())
        start = end - overlap  # 下一块起点回退 overlap，保持上下文连贯

    return [c for c in chunks if c]  # 过滤空块
