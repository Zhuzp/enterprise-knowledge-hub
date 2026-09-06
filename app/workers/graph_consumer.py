import asyncio
import json
import logging

import aio_pika
from aio_pika import ExchangeType
from sqlalchemy import select

from app.core.settings import settings
from app.infra.db import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from app.services.graph_service import process_graph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process(requeue=False):
        payload = json.loads(message.body.decode("utf-8"))
        document_id = payload["document_id"]
        logger.info("graph consumer 收到: %s", document_id)

        async with AsyncSessionLocal() as db:
            doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
            if not doc:
                logger.warning("文档不存在: %s", document_id)
                return
            if doc.status == DocumentStatus.READY.value:
                logger.info("文档已是 ready，跳过: %s", document_id)
                return
            if doc.status == DocumentStatus.FAILED.value:
                logger.info("文档已是 failed，跳过: %s", document_id)
                return

            try:
                count = await process_graph(document_id, db)
                await db.commit()
                logger.info("graph 处理完成 doc=%s entities_chunks=%s", document_id, count)
            except Exception:
                logger.exception("graph 处理失败 doc=%s", document_id)
                await db.rollback()
                doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
                if doc:
                    doc.status = DocumentStatus.FAILED.value
                    await db.commit()


async def main() -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)

    exchange = await channel.declare_exchange(settings.rabbitmq_exchange, ExchangeType.FANOUT, durable=True)
    queue = await channel.declare_queue(settings.rabbitmq_graph_queue, durable=True)
    await queue.bind(exchange)

    await queue.consume(handle_message)
    logger.info("graph consumer 已启动，监听 %s", settings.rabbitmq_graph_queue)
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())