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
          # ① 审核通过 → vector + graph（现有 fanout）
        pub_exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange, ExchangeType.FANOUT, durable=True
        )
        for queue_name in (settings.rabbitmq_vector_queue, settings.rabbitmq_graph_queue):
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.bind(pub_exchange)
        # ② 上传完成 → parse light/heavy（新增 direct）
        upload_exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange_uploaded, ExchangeType.DIRECT, durable=True
        )
        # 循环声明两个业务队列，全部持久化，绑定到交换机
        for queue_name in (settings.rabbitmq_parse_light_queue, settings.rabbitmq_parse_heavy_queue):
            queue = await channel.declare_queue(queue_name, durable=True)
            await queue.bind(upload_exchange, routing_key=queue_name)

def _is_heavy_file_type(file_type: str) -> bool:
    heavy = {x.strip().lower() for x in settings.parse_heavy_file_types.split(",")}
    return file_type.lower() in heavy

async def publish_document_uploaded(document_id: int, file_type: str) -> None:
    """上传成功后触发解析"""
    # 根据文件类型，选择重任务队列 / 轻任务队列
    routing_key = (
        settings.rabbitmq_parse_heavy_queue
        if _is_heavy_file_type(file_type)
        else settings.rabbitmq_parse_light_queue
    )
    # 建立rabbitmq长连接（connect_robust：断线自动重连）
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        # 声明直连交换机，持久化
        exchange = await channel.declare_exchange(
            settings.rabbitmq_exchange_uploaded, ExchangeType.DIRECT, durable=True
        )
        # 组装事件消息体
        body = json.dumps(
            {
                "event": "document.uploaded",
                "document_id": document_id,
                "file_type": file_type,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        # 发布持久消息到交换机，通过routing_key路由到对应队列
        await exchange.publish(
            Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=routing_key,
        )



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