"""Shared test setup.

Set OPENAI_API_KEY at module import time so settings can construct, and
silence the OTel exporter so tests don't try to dial Jaeger.
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "test")

import pytest


@pytest.fixture(autouse=True)
def _silent_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("promptwall.telemetry.configure", lambda _settings: None)
