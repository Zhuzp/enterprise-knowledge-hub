# app/workers/parse_consumer.py

import argparse
import asyncio
import json
import logging

import aio_pika
from aio_pika import ExchangeType
from sqlalchemy import select

from app.core.settings import settings
from app.infra.db import AsyncSessionLocal
from app.models.document import Document
from app.parsing.schemas import ParseStatus
from app.services.parse_service import run_document_parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process(requeue=False):
        payload = json.loads(message.body.decode("utf-8"))
        document_id = payload["document_id"]
        logger.info("parse consumer 收到 doc=%s payload=%s", document_id, payload)

        async with AsyncSessionLocal() as db:
            doc = (await db.execute(
                select(Document).where(Document.id == document_id)
            )).scalar_one_or_none()
            if not doc:
                logger.warning("文档不存在 doc=%s", document_id)
                return
            if doc.parse_status == ParseStatus.PARSED.value:
                logger.info("已 parsed，跳过 doc=%s", document_id)
                return

            try:
                await run_document_parse(document_id, db)
                await db.commit()
                logger.info("parse 成功 doc=%s", document_id)
            except Exception:
                logger.exception("parse 失败 doc=%s", document_id)
                await db.rollback()
                doc = (await db.execute(
                    select(Document).where(Document.id == document_id)
                )).scalar_one_or_none()
                if doc:
                    doc.parse_status = ParseStatus.FAILED.value
                    await db.commit()


async def main(queue_name: str) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)  # 视频一次处理一个

    exchange = await channel.declare_exchange(
        settings.rabbitmq_exchange_uploaded, ExchangeType.DIRECT, durable=True
    )
    queue = await channel.declare_queue(queue_name, durable=True)
    await queue.bind(exchange, routing_key=queue_name)
    await queue.consume(handle_message)

    logger.info("parse consumer 启动，监听 %s", queue_name)
    await asyncio.Future()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--queue",
        default=settings.rabbitmq_parse_light_queue,
        choices=[settings.rabbitmq_parse_light_queue, settings.rabbitmq_parse_heavy_queue],
    )
    args = parser.parse_args()
    asyncio.run(main(args.queue))