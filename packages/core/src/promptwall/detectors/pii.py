"""PII detector — Microsoft Presidio's analyzer plus a Canadian SIN recognizer.

Presidio's ``AnalyzerEngine`` loads spaCy at construction; building one
instance is heavy. Construct ``PIIDetector`` once at startup (or in a
session-scoped fixture for tests) and call ``scan`` repeatedly.

The custom ``_SINRecognizer`` adds Canadian Social Insurance Number
support with a Luhn checksum, suppressing false positives on arbitrary
9-digit sequences.
"""

import asyncio
import logging
import time
from collections.abc import Sequence

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

from promptwall.detectors.base import DetectorResult, ScanContext, Span

# Presidio is noisy at INFO; bring it down so structlog stays readable.
logging.getLogger("presidio-analyzer").setLevel(logging.WARNING)

_MS_PER_SECOND = 1000.0
_SIN_DIGITS = 9
_DEFAULT_ENTITIES: tuple[str, ...] = (
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IP_ADDRESS",
    "IBAN_CODE",
    "CA_SIN",
)


def _luhn_ok(digits: str) -> bool:
    """Return True iff ``digits`` (9 chars, all digits) passes the Luhn check."""
    if len(digits) != _SIN_DIGITS or not digits.isdigit():
        return False
    total = 0
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:  # noqa: PLR2004 -- Luhn fold rule
                value -= 9
        total += value
    return total % 10 == 0


class _SINRecognizer(PatternRecognizer):
    """Canadian Social Insurance Number with Luhn validation."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CA_SIN",
            patterns=[
                Pattern(
                    name="ca_sin",
                    regex=r"\b\d{3}[- ]?\d{3}[- ]?\d{3}\b",
                    score=0.4,
                ),
            ],
            context=["sin", "social insurance", "insurance number"],
            supported_language="en",
        )

    def validate_result(self, pattern_text: str) -> bool:
        """Return True iff the matched digits pass the Luhn checksum."""
        digits = "".join(c for c in pattern_text if c.isdigit())
        return _luhn_ok(digits)


class PIIDetector:
    """Presidio analyzer + custom SIN recognizer."""

    name = "pii"

    def __init__(
        self,
        *,
        timeout_ms: int = 100,
        entities: Sequence[str] = _DEFAULT_ENTITIES,
    ) -> None:
        self.timeout_ms = timeout_ms
        self._entities = list(entities)
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            },
        )
        self._engine = AnalyzerEngine(nlp_engine=provider.create_engine())
        self._engine.registry.add_recognizer(_SINRecognizer())

    async def scan(self, text: str, _ctx: ScanContext) -> DetectorResult:
        """Run the analyzer against ``text``."""
        start = time.perf_counter()
        # Let Presidio detect everything its registered recognizers know about;
        # narrow to our entity list afterwards. Passing entities= into analyze()
        # skips recognizers whose supported_entities don't include the requested
        # set, which silently disables PhoneRecognizer / UsSsnRecognizer in some
        # configurations.
        raw = await asyncio.to_thread(
            self._engine.analyze,
            text=text,
            language="en",
        )
        wanted = set(self._entities)
        results = [r for r in raw if r.entity_type in wanted]
        spans = [Span(start=r.start, end=r.end, label=r.entity_type) for r in results]
        latency_ms = (time.perf_counter() - start) * _MS_PER_SECOND
        return DetectorResult(
            detector=self.name,
            score=1.0 if results else 0.0,
            matched=bool(results),
            spans=spans,
            metadata={"entities": sorted({r.entity_type for r in results})},
            latency_ms=latency_ms,
        )
