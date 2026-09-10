import asyncio
import json
import logging

import aio_pika
from aio_pika import ExchangeType
from sqlalchemy import select

from app.core.settings import settings
from app.infra.db import AsyncSessionLocal
from app.models.document import Document, DocumentStatus
from app.services.vector_service import process_vector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process(requeue=False):
        payload = json.loads(message.body.decode("utf-8"))
        document_id = payload["document_id"]
        logger.info("vector consumer 收到: %s", document_id)

        async with AsyncSessionLocal() as db:
            doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
            if not doc:
                logger.warning("文档不存在: %s", document_id)
                return
            if doc.vector_done:
                logger.info("vector 已完成，跳过: %s", document_id)
                return
            if doc.status == DocumentStatus.FAILED.value:
                logger.info("文档已是 failed，跳过: %s", document_id)
                return

            doc.status = DocumentStatus.PROCESSING.value
            await db.commit()

            try:
                count = await process_vector(document_id, db)
                await db.commit()
                logger.info("vector 处理完成 doc=%s chunks=%s", document_id, count)
            except Exception as exc:
                logger.exception("vector 处理失败 doc=%s", document_id)
                await db.rollback()
                doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
                if doc:
                    meta = dict(doc.parse_metadata or {})
                    meta["vector_error"] = str(exc)[:500]
                    doc.parse_metadata = meta
                    doc.vector_done = False
                    doc.status = DocumentStatus.PROCESSING.value
                    await db.commit()


async def main() -> None:
    # 健壮连接，断连自动重连
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    # prefetch_count=1：一次只拿1条消息，处理完再收下一条，避免worker被压垮
    await channel.set_qos(prefetch_count=1)

    # 声明fanout交换机，持久化
    exchange = await channel.declare_exchange(settings.rabbitmq_exchange, ExchangeType.FANOUT, durable=True)
    # 声明持久队列
    queue = await channel.declare_queue(settings.rabbitmq_vector_queue, durable=True)
    # 队列绑定交换机
    # 防御性幂等操作，bind 不会重复创建绑定，安全无害，代价是代码看上去重复
    await queue.bind(exchange)
    # 注册消费回调
    await queue.consume(handle_message)
    logger.info("vector consumer 已启动，监听 %s", settings.rabbitmq_vector_queue)
    # 永久阻塞，等待消息
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())