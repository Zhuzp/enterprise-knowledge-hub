import httpx

from app.ai.retrievers.schemas import ChunkHit
from app.core.settings import settings


async def rerank_hits(
    query: str,
    candidates: list[ChunkHit],
    top_n: int | None = None,
) -> list[ChunkHit]:
    """用 qwen3-rerank 对 RRF 融合后的候选 chunk 精排"""
    # 边界判断：没有候选 或者 配置关闭重排，直接原样返回候选，不走重排服务
    if not candidates or not settings.rerank_enabled:
        return candidates

    # 优先用传入top_n，没有就读取配置文件的默认重排返回条数
    top_n = top_n or settings.rerank_top_n
    # 把候选ChunkHit里的文本内容提取出来，传给rerank服务
    documents = [c.content for c in candidates]

    # 拼接接口地址，rstrip('/')避免出现 //reranks 这种错误路径
    url = f"{settings.rerank_base_url.rstrip('/')}/reranks"
    # 请求体 payload，适配通义Qwen3‑Rerank OpenAI兼容接口格式
    payload = {
        "model": settings.rerank_model,
        "query": query, # 用户原始查询语句
        "documents": documents, # 需要打分的文档片段数组，顺序和candidates一一对应
        "top_n": min(top_n, len(documents)), # 不能大于候选总数，防止越界
    }

    # httpx异步客户端，超时30秒；async with自动关闭连接
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        # 如果http状态码4xx/5xx，直接抛出异常，上层需要捕获
        resp.raise_for_status()
        data = resp.json()

    # 取出重排结果数组
    results = data.get("results") or []
    reranked: list[ChunkHit] = []
    # ⚠️重点：rerank接口返回item["index"] 对应传入documents数组的下标
    # 依靠这个下标找回原始 candidates 对象，不会丢失元数据：metadata、doc_id等
    for item in results:
        idx = item["index"]
        hit = candidates[idx]
        # 使用rerank返回的相关性分数覆盖旧分数；拿不到分数就保留原来RRF/向量分数做兜底
        hit.score = float(item.get("relevance_score", hit.score))
        reranked.append(hit)
    # 返回已经按相关性从高到低排好序的ChunkHit列表
    return reranked
