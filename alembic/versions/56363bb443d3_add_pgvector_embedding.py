"""add pgvector embedding

Revision ID: 56363bb443d3
Revises: d69fe003971e
Create Date: 2026-09-03 12:38:30.730856

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56363bb443d3'
down_revision: Union[str, Sequence[str], None] = 'd69fe003971e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 维度和 settings.embedding_dims 保持一致
EMBEDDING_DIMS = 1024
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        f"ALTER TABLE document_chunks ADD COLUMN embedding vector({EMBEDDING_DIMS})"
    )
    # 数据量 < 1 万可先注释掉索引，小项目暴力扫描够用
    op.execute(
        f"""
        CREATE INDEX ix_document_chunks_embedding
        ON document_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS embedding")