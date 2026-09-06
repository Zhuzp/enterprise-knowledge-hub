import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.auth import router as auth_router
from app.api.v1.chat import router as chat_router
from app.api.v1.documents import router as documents_router
from app.api.v1.graph import router as graph_router
from app.api.v1.review import router as review_router
from app.api.v1.search import router as search_router
from app.api.v1.stats import router as stats_router
from app.infra.neo4j_client import close_driver, init_constraints
from app.infra.rabbitmq_client import setup_rabbitmq

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_constraints()
    try:
        await setup_rabbitmq()
    except Exception as exc:
        logger.warning("RabbitMQ 初始化失败，审核发布功能不可用: %s", exc)
    yield
    close_driver()

#lifespan 是 FastAPI 的生命周期钩子函数，启动时调用一次
app = FastAPI(title="Enterprise Knowledge Hub", lifespan=lifespan)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(documents_router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(search_router, prefix="/api/v1/search", tags=["search"])
app.include_router(chat_router, prefix="/api/v1/chat", tags=["chat"])
app.include_router(stats_router, prefix="/api/v1/stats", tags=["stats"])
app.include_router(graph_router, prefix="/api/v1/graph", tags=["graph"])
app.include_router(review_router, prefix="/api/v1/review", tags=["review"])


@app.get("/health")
def health():
    return {"status": "ok"}
