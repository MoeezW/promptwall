"""Persistence schema.

Each table is migration debt — add new ones sparingly and only when there's
a caller that needs the column. v0.1 only persists the request envelope;
response bodies, detector outputs, and policy decisions arrive in later
phases when the producers exist.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class RequestRecord(SQLModel, table=True):
    """One row per proxied request.

    The ``request_hash`` is SHA-256 of the canonical JSON payload. Content
    is intentionally not logged here — that lives behind a config flag so
    operators can stay compliant by default.
    """

    __tablename__ = "requests"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_hash: str = Field(index=True, max_length=64)
    model: str = Field(max_length=128)
    latency_ms: float
    status: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
