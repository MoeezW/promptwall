from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from promptwall.models import RequestRecord
from promptwall.providers.openai import OpenAIAdapter
from promptwall.proxy import app, get_adapter, get_session
from promptwall.settings import Settings


class _CapturingSession:
    """Stand-in for an AsyncSession that just records what was added."""

    def __init__(self, sink: list[RequestRecord]) -> None:
        self._sink = sink

    def add(self, record: object) -> None:
        if isinstance(record, RequestRecord):
            self._sink.append(record)

    async def commit(self) -> None:
        return None


@pytest.fixture
def captured() -> list[RequestRecord]:
    return []


@pytest.fixture
def client(captured):
    settings = Settings()
    adapter = OpenAIAdapter(settings)

    async def _stub_session() -> AsyncIterator[_CapturingSession]:
        yield _CapturingSession(captured)

    app.dependency_overrides[get_adapter] = lambda: adapter
    app.dependency_overrides[get_session] = _stub_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_chat_completions_happy_path(client, captured):
    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"id": "chatcmpl-stub", "object": "chat.completion", "choices": []},
            )
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["id"] == "chatcmpl-stub"
    assert len(captured) == 1
    record = captured[0]
    assert record.model == "gpt-4o-mini"
    assert record.status == 200
    assert len(record.request_hash) == 64
    assert record.latency_ms >= 0


def test_chat_completions_forwards_upstream_error_status(client, captured):
    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(429, json={"error": {"message": "slow down"}})
        )

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )

    assert response.status_code == 429
    assert response.json()["error"]["message"] == "slow down"
    assert captured[0].status == 429
