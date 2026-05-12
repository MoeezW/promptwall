"""initial.

Revision ID: 7787cfbef00d
Revises:
Create Date: 2026-05-11 01:58:41.666066
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7787cfbef00d"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
