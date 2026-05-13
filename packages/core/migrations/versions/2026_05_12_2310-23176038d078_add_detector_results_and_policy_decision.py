"""add detector_results and policy_decision.

Revision ID: 23176038d078
Revises: ce1c93751bc9
Create Date: 2026-05-12 23:10:30.537977
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "23176038d078"
down_revision: str | Sequence[str] | None = "ce1c93751bc9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("detector_results", sa.JSON(), nullable=True))
    op.add_column("requests", sa.Column("policy_decision", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("requests", "policy_decision")
    op.drop_column("requests", "detector_results")
