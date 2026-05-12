from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from promptwall.detectors.base import Span
from promptwall.redaction import _TOKEN_PATTERN, RedactionMap, hydrate, redact


def _spans_for(text: str, *substrs_with_label: tuple[str, str]) -> list[Span]:
    """Build Span objects by finding each (substr, label) in text."""
    spans: list[Span] = []
    cursor = 0
    for substr, label in substrs_with_label:
        idx = text.find(substr, cursor)
        if idx >= 0:
            spans.append(Span(start=idx, end=idx + len(substr), label=label))
            cursor = idx + len(substr)
    return spans


def test_redact_replaces_span_with_token():
    text = "Email me at jane@example.com soon."
    spans = _spans_for(text, ("jane@example.com", "EMAIL_ADDRESS"))
    redacted, mapping = redact(text, spans)
    assert "jane@example.com" not in redacted
    assert "<PII:EMAIL_ADDRESS_" in redacted
    assert len(mapping.tokens) == 1


def test_token_is_deterministic_for_same_salt_and_value():
    salt = b"\x00" * 32
    text = "x = jane@example.com"
    spans = _spans_for(text, ("jane@example.com", "EMAIL_ADDRESS"))
    r1, _ = redact(text, spans, map_into=RedactionMap(salt=salt))
    r2, _ = redact(text, spans, map_into=RedactionMap(salt=salt))
    assert r1 == r2


def test_token_differs_across_salts():
    text = "jane@example.com"
    spans = _spans_for(text, ("jane@example.com", "EMAIL_ADDRESS"))
    r1, _ = redact(text, spans, map_into=RedactionMap(salt=b"\x01" * 32))
    r2, _ = redact(text, spans, map_into=RedactionMap(salt=b"\x02" * 32))
    assert r1 != r2


def test_hydrate_restores_original():
    text = "Contact jane@example.com or 555-555-5555."
    spans = _spans_for(
        text,
        ("jane@example.com", "EMAIL_ADDRESS"),
        ("555-555-5555", "PHONE_NUMBER"),
    )
    redacted, mapping = redact(text, spans)
    assert hydrate(redacted, mapping.tokens) == text


def test_unknown_token_in_response_is_left_alone():
    """Model hallucinates a token; we must not substitute it."""
    hallucinated = "<PII:EMAIL_aabbccdd>"
    out = hydrate(f"You said {hallucinated} earlier.", tokens={})
    assert hallucinated in out


def test_overlapping_spans_dont_double_replace():
    text = "abc"
    spans = [
        Span(start=0, end=3, label="A"),
        Span(start=1, end=3, label="B"),  # overlaps; should be skipped
    ]
    redacted, mapping = redact(text, spans)
    assert len(mapping.tokens) == 1
    assert hydrate(redacted, mapping.tokens) == text


def test_empty_spans_returns_text_unchanged():
    text = "no PII here"
    redacted, mapping = redact(text, [])
    assert redacted == text
    assert mapping.tokens == {}


# --- the most important test in the codebase ---


_PII_VALUES = st.sampled_from(
    [
        "jane@example.com",
        "joe.smith+test@corp.co.uk",
        "+1 (415) 555-0132",
        "4111 1111 1111 1111",
        "527-43-9182",
        "046-454-286",
        "192.168.1.42",
        "GB82 WEST 1234 5698 7654 32",
    ]
)
_PII_LABELS = st.sampled_from(
    ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN", "CA_SIN", "IP_ADDRESS"]
)
# Avoid characters that could collide with the token format (angle brackets).
_FILLER = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        blacklist_characters="<>",
        max_codepoint=0x10000,
    ),
    min_size=0,
    max_size=40,
)


@st.composite
def _text_with_pii(draw: st.DrawFn) -> tuple[str, list[tuple[str, str]]]:
    """Build a text string with embedded PII values; return (text, [(value, label), ...])."""
    n_pii = draw(st.integers(min_value=0, max_value=4))
    chunks: list[str] = [draw(_FILLER)]
    inserted: list[tuple[str, str]] = []
    for _ in range(n_pii):
        value = draw(_PII_VALUES)
        label = draw(_PII_LABELS)
        chunks.append(value)
        chunks.append(draw(_FILLER))
        inserted.append((value, label))
    return "".join(chunks), inserted


@given(case=_text_with_pii())
@hyp_settings(max_examples=100, deadline=None)
def test_redact_then_hydrate_is_identity(case: tuple[str, list[tuple[str, str]]]):
    """Round-trip property: hydrate(redact(text)) == text for any text + spans."""
    text, pieces = case
    spans = _spans_for(text, *pieces)
    redacted, mapping = redact(text, spans)
    assert hydrate(redacted, mapping.tokens) == text
    # No token should leak into the redacted output without a mapping entry.
    for match in _TOKEN_PATTERN.finditer(redacted):
        assert match.group(0) in mapping.tokens


@given(noise=_FILLER, fake_hmac=st.text(alphabet="0123456789abcdef", min_size=8, max_size=8))
@hyp_settings(max_examples=50, deadline=None)
def test_hallucinated_tokens_are_not_hydrated(noise: str, fake_hmac: str):
    """A model can mint look-alike tokens; if HMAC is unknown, leave them alone."""
    fake = f"<PII:EMAIL_{fake_hmac}>"
    body = f"{noise} {fake} {noise}"
    assert hydrate(body, tokens={}) == body
