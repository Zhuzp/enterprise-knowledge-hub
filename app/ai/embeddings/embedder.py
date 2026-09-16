from openai import AsyncOpenAI

from app.core.settings import settings

_client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.openai_base_url,
)


# 单个文本 → embedding 向量
async def embed_text(text: str) -> list[float]:
    resp = await _client.embeddings.create(
        model=settings.embedding_model,
        input=text,
        dimensions=settings.embedding_dims,
    )
    return resp.data[0].embedding


# 批量文本列表 → 向量列表
# text-embedding-v4 单批最多 10 条
EMBED_BATCH_SIZE = 10


async def embed_texts(texts: list[str]) -> list[list[float]]:
    # 空输入直接返回空列表
    if not texts:
        return []
    all_vectors: list[list[float]] = []
    # 按 EMBED_BATCH_SIZE 做切片，分批调用接口
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        # 异步请求 embedding 接口，传入整批文本
        resp = await _client.embeddings.create(
            model=settings.embedding_model,
            input=batch,
            dimensions=settings.embedding_dims,
        )
        # 重点：按返回的index排序，保证向量顺序和输入文本顺序一致
        all_vectors.extend(
            item.embedding for item in sorted(resp.data, key=lambda x: x.index)
        )
    return all_vectors
