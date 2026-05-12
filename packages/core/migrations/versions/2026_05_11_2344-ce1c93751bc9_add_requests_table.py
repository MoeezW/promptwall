"""add requests table.

Revision ID: ce1c93751bc9
Revises: 7787cfbef00d
Create Date: 2026-05-11 23:44:54.592849
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "ce1c93751bc9"
down_revision: str | Sequence[str] | None = "7787cfbef00d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_requests_request_hash"),
        "requests",
        ["request_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_requests_request_hash"), table_name="requests")
    op.drop_table("requests")
