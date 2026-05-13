"""Persistence schema.

Each table is migration debt — add new ones sparingly and only when there's
a caller that needs the column. v0.1 persists the request envelope plus a
JSON snapshot of detector results and the policy decision so the dashboard
has something to render. Response bodies stay out of Postgres in v0.1.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class RequestRecord(SQLModel, table=True):
    """One row per proxied request.

    The ``request_hash`` is SHA-256 of the canonical JSON payload. Content
    is intentionally not logged here — that lives behind a config flag so
    operators can stay compliant by default. ``detector_results`` is a
    JSON array of ``DetectorResult`` snapshots; ``policy_decision`` is a
    JSON object with the action / reason / matched_rule_index.
    """

    __tablename__ = "requests"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    request_hash: str = Field(index=True, max_length=64)
    model: str = Field(max_length=128)
    latency_ms: float
    status: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detector_results: list[dict[str, object]] | None = Field(
        default=None,
        sa_column=Column("detector_results", JSON, nullable=True),
    )
    policy_decision: dict[str, object] | None = Field(
        default=None,
        sa_column=Column("policy_decision", JSON, nullable=True),
    )
