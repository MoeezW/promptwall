import pytest

from promptwall.detectors.base import ScanContext
from promptwall.detectors.pii import PIIDetector, _luhn_ok

_CTX = ScanContext(request_id="test", direction="input")

_POSITIVE = (
    "Email me at jane.doe@example.com about the proposal.",
    "Call me at +1 (415) 555-0132 tomorrow morning.",
    "My credit card is 4111 1111 1111 1111, expires next year.",
    # 527-43-9182 is not on Presidio's invalidate_result placeholder list (000/666/123456789/etc.)
    "His US SSN is 527-43-9182, please update the records.",
    "Connect to the server at 192.168.1.42 over SSH.",
    "Wire it to IBAN GB82 WEST 1234 5698 7654 32 by Friday.",
    # CA_SIN — 046-454-286 is a Luhn-valid test SIN
    "Update the SIN in the file to 046-454-286 for that customer.",
)

_NEGATIVE = (
    "What's the weather forecast for Toronto this weekend?",
    "Explain how transformers work at a high level.",
    "Recommend a good Italian restaurant downtown.",
    "Summarize the latest news on climate policy.",
    "Convert 100 kilometres into miles.",
    "Write a haiku about a rainy afternoon.",
)


@pytest.fixture(scope="module")
def detector() -> PIIDetector:
    return PIIDetector()


@pytest.mark.parametrize("text", _POSITIVE)
async def test_positive_cases_detected(detector, text):
    result = await detector.scan(text, _CTX)
    assert result.matched is True, f"failed to detect PII in: {text!r}"
    assert result.score == 1.0
    assert result.spans


@pytest.mark.parametrize("text", _NEGATIVE)
async def test_negative_cases_clean(detector, text):
    result = await detector.scan(text, _CTX)
    assert result.matched is False, f"false positive: {text!r}"
    assert result.score == 0.0


async def test_ca_sin_is_recognized_as_its_own_entity(detector):
    result = await detector.scan(
        "Update SIN to 046-454-286 for that customer.",
        _CTX,
    )
    entities = result.metadata["entities"]
    assert "CA_SIN" in entities


def test_luhn_rejects_random_nine_digits():
    # Random nine digits not in Luhn form.
    assert _luhn_ok("123456789") is False


def test_luhn_accepts_known_good_sin():
    assert _luhn_ok("046454286") is True


def test_luhn_rejects_non_nine_digit_input():
    assert _luhn_ok("12345") is False
    assert _luhn_ok("1234567890") is False
    assert _luhn_ok("abc123def") is False
