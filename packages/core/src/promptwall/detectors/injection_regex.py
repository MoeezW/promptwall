"""Regex-based prompt-injection detector.

Curated pattern pack drawn from HackAPrompt, JailbreakBench, and public
prompt-injection corpora (OWASP LLM Top 10). The patterns are precise
but recall is moderate — the ML detector in Phase 3 fills the gap.

Each pattern contributes a weight; the total saturates at ``1.0``.
"""

import re
import time
from collections.abc import Sequence
from re import Pattern

from promptwall.detectors.base import DetectorResult, ScanContext, Span

_MATCHED_THRESHOLD = 0.5
_MS_PER_SECOND = 1000.0


def _compile(patterns: Sequence[tuple[str, float]]) -> tuple[tuple[Pattern[str], float], ...]:
    return tuple((re.compile(p, re.IGNORECASE), w) for p, w in patterns)


# Weights are tuned conservatively: one regex hit alone is "noticed but not
# blocked" at a typical 0.8 policy threshold; multiple hits compound and
# saturate. Patterns drawn from observed jailbreaks — keeping the set small
# and high-signal beats sprinkling weak patterns.
_PATTERNS = _compile(
    (
        # Direct override attempts
        (
            r"ignore (?:the|all|any|your) (?:previous|above|prior|preceding) "
            r"(?:instructions|prompt|rules|directions)",
            0.7,
        ),
        (
            r"disregard (?:the|all|any|your) (?:previous|above|prior|preceding) "
            r"(?:instructions|prompt|rules)",
            0.7,
        ),
        (r"forget (?:everything|all|the) (?:above|before|previous|prior)", 0.6),
        # Role manipulation
        (r"\byou are now\b", 0.4),
        (r"\bact as (?:a |an |the )?(?:dan|developer|admin|root|jailbroken)", 0.7),
        (r"\bpretend (?:to be|you are|that you)\b", 0.4),
        # System-prompt exfiltration
        (
            r"\b(?:reveal|show|print|reproduce|repeat|output) (?:the|your) "
            r"(?:system|initial|original) (?:prompt|instructions)\b",
            0.8,
        ),
        (
            r"\bwhat (?:were|are) (?:the|your) (?:original|initial) " r"(?:instructions|prompt)",
            0.6,
        ),
        (r"\bwhat is (?:above|preceding|before this|written above)", 0.4),
        # Known jailbreak names
        (r"\b(?:DAN|do anything now)\b", 0.5),
        (r"\bjailbroken? mode\b", 0.6),
        (r"\bdeveloper mode\b", 0.5),
        # Delimiter / mode breaks
        (r"</?(?:system|admin|root|sys)>", 0.6),
        (r"###\s*(?:end|new|reset|admin)", 0.5),
        (r"\[INST\]|\[/INST\]", 0.4),
        # Instruction-override boilerplate
        (r"\bnew (?:instructions|prompt|rules)(?:\s*:|\.)", 0.5),
        (r"\boverride (?:safety|all|previous)", 0.6),
        (r"\bbypass (?:safety|filters?|the|all)", 0.6),
        # Encoded payloads
        (r"\bbase64 ?(?:decode|encoded)\b", 0.4),
        (r"\brot13\b", 0.3),
        # "Pretend the user said …" attacks
        (r"\b(?:respond|reply) as if (?:the user|i) (?:asked|said|wrote)\b", 0.5),
        # Data exfiltration
        (r"\bsend (?:your|the) (?:training|fine[- ]?tuning) data\b", 0.6),
        (r"\bleak (?:the|your|all) (?:data|prompt|secrets)\b", 0.7),
        # "No filter" attempts
        (r"\bwithout (?:any |the )?(?:filter|restriction|safety|censorship|warning)s?", 0.5),
        (r"\bunfiltered (?:response|reply|answer|mode)", 0.5),
        # Polite distraction wrappers
        (r"\bonly respond with (?:yes|no)\b", 0.3),
        (r"\boutput nothing (?:but|except)\b", 0.3),
        # Hypothetical framing
        (r"\bthis is just a (?:test|hypothetical|simulation)\b", 0.3),
        (r"\bin a hypothetical (?:world|scenario)\b", 0.3),
        # Imperative refusal probes
        (r"\bdo not (?:refuse|decline|apologize)\b", 0.4),
    )
)


class InjectionRegexDetector:
    """Score = saturating sum of matched pattern weights, clamped to 1.0."""

    name = "injection_regex"

    def __init__(self, timeout_ms: int = 50) -> None:
        self.timeout_ms = timeout_ms

    async def scan(self, text: str, _ctx: ScanContext) -> DetectorResult:
        """Run all patterns against ``text``."""
        start = time.perf_counter()
        total = 0.0
        spans: list[Span] = []
        labels: list[str] = []

        for pattern, weight in _PATTERNS:
            for match in pattern.finditer(text):
                total += weight
                label = pattern.pattern[:40]
                spans.append(Span(start=match.start(), end=match.end(), label=label))
                labels.append(label)

        score = min(1.0, total)
        latency_ms = (time.perf_counter() - start) * _MS_PER_SECOND
        return DetectorResult(
            detector=self.name,
            score=score,
            matched=score >= _MATCHED_THRESHOLD,
            spans=spans,
            metadata={"patterns_matched": len(labels)},
            latency_ms=latency_ms,
        )
