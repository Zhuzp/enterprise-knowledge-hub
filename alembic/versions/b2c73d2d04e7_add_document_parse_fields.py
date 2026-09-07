"""add document parse fields

Revision ID: b2c73d2d04e7
Revises: 56363bb443d3
Create Date: 2026-09-07 15:50:49.840585

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c73d2d04e7'
down_revision: Union[str, Sequence[str], None] = '56363bb443d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("documents", sa.Column("parse_status", sa.String(20), server_default="pending", nullable=False))
    op.add_column("documents", sa.Column("parse_error", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("parsed_markdown_key", sa.String(500), nullable=True))
    op.add_column("documents", sa.Column("parse_metadata", postgresql.JSONB, nullable=True))
    op.add_column("documents", sa.Column("media_category", sa.String(20), server_default="document", nullable=False))



def downgrade() -> None:
    """Downgrade schema."""
    pass
