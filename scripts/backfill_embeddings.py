"""用法: python -m scripts.backfill_embeddings"""

import asyncio

from sqlalchemy import select

from app.ai.embeddings.embedder import embed_text
from app.infra.db import AsyncSessionLocal
from app.models.document_chunk import DocumentChunk


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DocumentChunk).where(DocumentChunk.embedding.is_(None))
        )
        chunks = result.scalars().all()
        print(f"待回填: {len(chunks)}")
        for i, chunk in enumerate(chunks, 1):
            chunk.embedding = await embed_text(chunk.content)
            if i % 10 == 0:
                print(f"已处理 {i}/{len(chunks)}")
        await db.commit()
    print("完成")


if __name__ == "__main__":
    asyncio.run(main())