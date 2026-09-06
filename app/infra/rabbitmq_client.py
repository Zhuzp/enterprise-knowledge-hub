import json
from datetime import datetime, timezone

import aio_pika
from aio_pika import ExchangeType, Message

from app.core.settings import settings


async def setup_rabbitmq() -> None:
    "启动时声明 exchange 和两个 queue（API 启动时调用一次）"
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        # 声明持久 Fanout 交换机
        exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange,
            ExchangeType.FANOUT,
            durable=True,
        )
        # 循环声明两个业务队列，全部持久化，绑定到交换机
        for queue_name in (settings.rabbitmq_vector_queue, settings.rabbitmq_graph_queue):
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.bind(exchange)


async def publish_document_published(document_id: int) -> None:
    "审核通过后投递消息"
    # 1.建立TCP连接到RabbitMQ服务
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        # 2.创建channel信道
        channel = await connection.channel()
        # 3.幂等声明交换机（防止还没初始化就发消息）
        exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange,
            ExchangeType.FANOUT,
            durable=True,
        )
        # 4.构造事件消息体 json字节
        body = json.dumps(
            {
                "event": "document.published",  # 事件类型标识
                "document_id": document_id, # 业务主键
                "published_at": datetime.now(timezone.utc).isoformat(), # UTC时间戳
            },
            ensure_ascii=False,
        ).encode("utf-8")
        # 5.发布持久化消息到fanout交换机
        await exchange.publish(
            Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="",
        )