"""Dashboard read API.

Routes mounted on the same FastAPI app as the proxy so a single uvicorn
serves both ``/v1/chat/completions`` and ``/api/*``. The Next.js
dashboard uses Next's ``rewrites`` to proxy ``/api/*`` to this service,
which sidesteps CORS in dev.

Endpoints (v0.1):
- ``GET /api/requests`` — paginated list, newest first, optional
  ``action`` filter (allow / redact / block).
- ``GET /api/requests/{id}`` — full row including ``detector_results``
  and ``policy_decision`` JSON.
"""

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from promptwall.db import get_session
from promptwall.models import RequestRecord

router = APIRouter(prefix="/api", tags=["dashboard"])

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 200


class RequestSummary(BaseModel):
    """One row in the request list — light projection for the table view."""

    id: UUID
    request_hash: str
    model: str
    latency_ms: float
    status: int | None
    action: str | None
    created_at: datetime


class RequestListResponse(BaseModel):
    """Paginated wrapper around request summaries."""

    items: list[RequestSummary]
    total: int
    limit: int
    offset: int


class RequestDetail(BaseModel):
    """Full row for the detail page — includes detector_results + policy_decision."""

    id: UUID
    request_hash: str
    model: str
    latency_ms: float
    status: int | None
    created_at: datetime
    detector_results: list[dict[str, object]] | None
    policy_decision: dict[str, object] | None


def _summary(record: RequestRecord) -> RequestSummary:
    decision = record.policy_decision or {}
    action = decision.get("action") if isinstance(decision, dict) else None
    return RequestSummary(
        id=record.id,
        request_hash=record.request_hash,
        model=record.model,
        latency_ms=record.latency_ms,
        status=record.status,
        action=cast("str | None", action),
        created_at=record.created_at,
    )


@router.get("/requests")
async def list_requests(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = _DEFAULT_LIMIT,
    offset: int = 0,
    action: str | None = None,
) -> RequestListResponse:
    """Return the most recent requests, newest first."""
    limit = max(1, min(limit, _MAX_LIMIT))
    offset = max(0, offset)

    count_stmt = select(func.count()).select_from(RequestRecord)
    total = int((await session.execute(count_stmt)).scalar_one())

    stmt = (
        select(RequestRecord)
        .order_by(desc(RequestRecord.created_at))  # type: ignore[arg-type]
        .limit(limit)
        .offset(offset)
    )
    records = (await session.execute(stmt)).scalars().all()
    items = [_summary(r) for r in records]
    if action:
        items = [s for s in items if s.action == action]
    return RequestListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/requests/{request_id}")
async def get_request(
    request_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RequestDetail:
    """Return one request with its full detector + decision payload."""
    # SQLModel's instrumented attributes generate SQL at runtime; mypy sees
    # the value type (UUID) and flags the comparison. Standard SQLModel
    # pattern — silenced locally rather than relaxed project-wide.
    stmt = select(RequestRecord).where(RequestRecord.id == request_id)  # type: ignore[arg-type]
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=404, detail="request not found")
    return RequestDetail(
        id=record.id,
        request_hash=record.request_hash,
        model=record.model,
        latency_ms=record.latency_ms,
        status=record.status,
        created_at=record.created_at,
        detector_results=record.detector_results,
        policy_decision=record.policy_decision,
    )
