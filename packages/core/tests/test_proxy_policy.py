"""End-to-end test for Phase 4: detectors → policy → redact → forward → hydrate.

Phase 4 exit criterion: a prompt with a credit card is redacted before being
forwarded; the upstream response (which can echo the token) is hydrated back
to the original credit card before being returned to the client.
"""

import json
import re
from collections.abc import AsyncIterator

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from promptwall.config import Action, Policy, Rule
from promptwall.detectors.base import DetectorResult, ScanContext, Span
from promptwall.detectors.circuit import CircuitBreaker
from promptwall.models import RequestRecord
from promptwall.providers.openai import OpenAIAdapter
from promptwall.proxy import (
    app,
    get_adapter,
    get_breakers,
    get_detectors,
    get_policy,
    get_session,
)
from promptwall.settings import Settings


class _StubPII:
    """Returns a Span for any 16-digit credit-card-like substring."""

    name = "pii"
    timeout_ms = 100

    async def scan(self, text: str, _ctx: ScanContext) -> DetectorResult:
        match = re.search(r"\b(?:\d{4}[ -]?){3}\d{4}\b", text)
        if match:
            return DetectorResult(
                detector=self.name,
                score=1.0,
                matched=True,
                spans=[Span(start=match.start(), end=match.end(), label="CREDIT_CARD")],
                latency_ms=0.5,
            )
        return DetectorResult(
            detector=self.name,
            score=0.0,
            matched=False,
            latency_ms=0.5,
        )


class _StubSecrets:
    """Returns matched only when 'SECRET_KEY' appears literally."""

    name = "secrets"
    timeout_ms = 50

    async def scan(self, text: str, _ctx: ScanContext) -> DetectorResult:
        if "SECRET_KEY" in text:
            return DetectorResult(
                detector=self.name,
                score=1.0,
                matched=True,
                latency_ms=0.5,
            )
        return DetectorResult(
            detector=self.name,
            score=0.0,
            matched=False,
            latency_ms=0.5,
        )


class _CapturingSession:
    def __init__(self, sink: list[RequestRecord]) -> None:
        self._sink = sink

    def add(self, record: object) -> None:
        if isinstance(record, RequestRecord):
            self._sink.append(record)

    async def commit(self) -> None:
        return None


def _stub_policy(*rules: Rule) -> Policy:
    return Policy(rules=list(rules), default_action=Action.ALLOW, degraded_action=Action.BLOCK)


@pytest.fixture
def captured() -> list[RequestRecord]:
    return []


def _wire(
    captured_records: list[RequestRecord],
    policy: Policy,
    detectors: list[object],
) -> None:
    settings = Settings()
    adapter = OpenAIAdapter(settings)

    async def _stub_session() -> AsyncIterator[_CapturingSession]:
        yield _CapturingSession(captured_records)

    app.dependency_overrides[get_adapter] = lambda: adapter
    app.dependency_overrides[get_session] = _stub_session
    app.dependency_overrides[get_detectors] = lambda: detectors
    app.dependency_overrides[get_breakers] = lambda: {d.name: CircuitBreaker() for d in detectors}
    app.dependency_overrides[get_policy] = lambda: policy


@pytest.fixture
def client_with_redact(captured: list[RequestRecord]):
    policy = _stub_policy(
        Rule(condition="pii.matched", action=Action.REDACT, reason="redact PII"),
    )
    _wire(captured, policy, [_StubPII()])
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def client_with_block(captured: list[RequestRecord]):
    policy = _stub_policy(
        Rule(condition="secrets.matched", action=Action.BLOCK, reason="secret detected"),
    )
    _wire(captured, policy, [_StubSecrets()])
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_credit_card_is_redacted_before_forwarding_and_hydrated_on_return(
    client_with_redact,
    captured: list[RequestRecord],
):
    forwarded_payloads: list[dict[str, object]] = []

    def _echo_token_back(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        forwarded_payloads.append(payload)
        prompt = payload["messages"][-1]["content"]
        token_match = re.search(r"<PII:[A-Z_]+_[0-9a-f]{8}>", prompt)
        token = token_match.group(0) if token_match else ""
        assistant_msg = f"I see the card you mentioned: {token}. Got it."
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-stub",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": assistant_msg},
                        "finish_reason": "stop",
                    },
                ],
            },
        )

    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            side_effect=_echo_token_back,
        )

        client_response = client_with_redact.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": "My card is 4111 1111 1111 1111, please save it."},
                ],
            },
        )

    assert client_response.status_code == 200
    assert len(forwarded_payloads) == 1

    # Forwarded prompt has the token, not the original CC.
    forwarded_prompt = forwarded_payloads[0]["messages"][-1]["content"]
    assert "4111 1111 1111 1111" not in forwarded_prompt
    assert re.search(r"<PII:CREDIT_CARD_[0-9a-f]{8}>", forwarded_prompt)

    # Client received the original CC (token was hydrated back).
    body = client_response.json()
    assistant_text = body["choices"][0]["message"]["content"]
    assert "4111 1111 1111 1111" in assistant_text
    assert "<PII:" not in assistant_text

    # Request row was persisted with a 200 status.
    assert len(captured) == 1
    assert captured[0].status == 200


def test_secrets_in_prompt_block_the_request(
    client_with_block,
    captured: list[RequestRecord],
):
    """Block decisions never forward to the provider."""
    with respx.mock:
        # No mock set up; respx will fail if the proxy tries to forward.
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(500),
        )

        response = client_with_block.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "user", "content": "Here is my SECRET_KEY=abc; use it."},
                ],
            },
        )

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["type"] == "promptwall_policy_block"
    assert "secret" in body["error"]["message"].lower()

    # Persisted as 403, no upstream call made.
    assert len(captured) == 1
    assert captured[0].status == 403


def test_allow_path_does_not_redact_or_block(
    client_with_redact,
    captured: list[RequestRecord],
):
    """No PII in input → no redaction → straight passthrough."""
    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": "chatcmpl-clean",
                    "choices": [
                        {"message": {"role": "assistant", "content": "Hello, friend."}},
                    ],
                },
            ),
        )

        response = client_with_redact.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Tell me a joke."}],
            },
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Hello, friend."
    assert captured[0].status == 200
