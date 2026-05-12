"""Reversible PII redaction with HMAC-keyed tokens.

Each PII span is replaced with a deterministic token of the form
``<PII:{TYPE}_{HMAC8}>`` where HMAC8 is the first 8 hex characters of
``HMAC-SHA256(salt, original)``. The salt is per-request and never
leaves the proxy. The ``RedactionMap`` tracks the token→original
mapping; hydration consults it to substitute originals back.

Two things this guarantees:

1. ``hydrate(redact(text)) == text`` for any text and span set
   (verified by hypothesis property test).
2. A model that hallucinates a look-alike token like
   ``<PII:EMAIL_aabbccdd>`` won't get hydrated — only tokens with HMACs
   present in the mapping are substituted.

Persistence (encrypting the salt + mapping for audit) is a Phase 6+
concern; v0.1 keeps the mapping in memory per request.
"""

import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from promptwall.detectors.base import Span

_SALT_BYTES = 32
_HMAC_HEX_CHARS = 8
_DEFAULT_TYPE = "PII"
_TOKEN_PATTERN = re.compile(r"<PII:([A-Z_]+)_([0-9a-f]{8})>")
_NON_TYPE_CHAR = re.compile(r"[^A-Z_]")


@dataclass
class RedactionMap:
    """Per-request token-to-original mapping plus the HMAC salt."""

    salt: bytes
    tokens: dict[str, str] = field(default_factory=dict)

    @classmethod
    def new(cls) -> "RedactionMap":
        """Construct a map with a fresh cryptographic salt."""
        return cls(salt=secrets.token_bytes(_SALT_BYTES))


def _hmac8(salt: bytes, value: str) -> str:
    digest = hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:_HMAC_HEX_CHARS]


def _make_token(entity_type: str, salt: bytes, value: str) -> str:
    normalized = _NON_TYPE_CHAR.sub("_", entity_type.upper()) or _DEFAULT_TYPE
    return f"<PII:{normalized}_{_hmac8(salt, value)}>"


def redact(
    text: str,
    spans: Sequence[Span],
    *,
    map_into: RedactionMap | None = None,
) -> tuple[str, RedactionMap]:
    """Replace each span in ``text`` with a stable HMAC token.

    Returns the redacted text and the (mutated) mapping. Pass ``map_into``
    to accumulate mappings across multiple ``redact`` calls (e.g., redacting
    each chat message into a single per-request mapping).
    """
    mapping = map_into if map_into is not None else RedactionMap.new()
    if not spans:
        return text, mapping

    sorted_spans = sorted(spans, key=lambda s: (s.start, s.end))
    out: list[str] = []
    cursor = 0
    for span in sorted_spans:
        if span.start < cursor:
            # Overlapping span; the earlier (broader) one wins.
            continue
        if span.end > len(text) or span.start < 0:
            continue
        out.append(text[cursor : span.start])
        original = text[span.start : span.end]
        token = _make_token(span.label or _DEFAULT_TYPE, mapping.salt, original)
        mapping.tokens[token] = original
        out.append(token)
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out), mapping


def hydrate(text: str, tokens: Mapping[str, str]) -> str:
    """Replace known tokens in ``text`` with their originals.

    Unknown tokens (look-alikes the model hallucinated) are left as-is.
    """
    if not tokens:
        return text

    def _replace(match: re.Match[str]) -> str:
        return tokens.get(match.group(0), match.group(0))

    return _TOKEN_PATTERN.sub(_replace, text)
