"""Secrets detector — thin wrapper around Yelp's ``detect-secrets``.

detect-secrets is file-oriented: the public entry points all take paths.
We write the input to a tempfile, run ``SecretsCollection.scan_file``,
then map the line-numbered findings back to character spans in the
original text. The blocking scan runs in a thread so the event loop
stays responsive.
"""

import asyncio
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path

from detect_secrets.core.potential_secret import PotentialSecret
from detect_secrets.core.secrets_collection import SecretsCollection
from detect_secrets.settings import default_settings

from promptwall.detectors.base import DetectorResult, ScanContext, Span

_MS_PER_SECOND = 1000.0


def _scan_blocking(text: str) -> list[PotentialSecret]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        delete=False,
        suffix=".txt",
        encoding="utf-8",
    ) as tmp:
        tmp.write(text)
        tmp_path = tmp.name
    try:
        with default_settings():
            collection = SecretsCollection()
            collection.scan_file(tmp_path)
        return [secret for _filepath, secret in collection]
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _findings_to_spans(text: str, findings: Iterable[PotentialSecret]) -> list[Span]:
    findings_list = list(findings)
    if not findings_list:
        return []
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    spans: list[Span] = []
    for hit in findings_list:
        idx = hit.line_number - 1
        if 0 <= idx < len(lines):
            start = offsets[idx]
            end = start + len(lines[idx].rstrip("\r\n"))
            spans.append(Span(start=start, end=end, label=hit.type))
    return spans


class SecretsDetector:
    """detect-secrets' default plugin pack — AWS keys, GitHub tokens, etc."""

    name = "secrets"

    def __init__(self, timeout_ms: int = 200) -> None:
        self.timeout_ms = timeout_ms

    async def scan(self, text: str, _ctx: ScanContext) -> DetectorResult:
        """Scan ``text`` for high-confidence secret tokens."""
        start = time.perf_counter()
        findings = await asyncio.to_thread(_scan_blocking, text)
        spans = _findings_to_spans(text, findings)
        latency_ms = (time.perf_counter() - start) * _MS_PER_SECOND
        return DetectorResult(
            detector=self.name,
            score=1.0 if findings else 0.0,
            matched=bool(findings),
            spans=spans,
            metadata={"secret_types": sorted({f.type for f in findings})},
            latency_ms=latency_ms,
        )
