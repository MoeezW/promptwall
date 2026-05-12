import pytest

from promptwall.detectors.base import ScanContext
from promptwall.detectors.secrets import SecretsDetector

_CTX = ScanContext(request_id="test", direction="input")

# Test cases use clearly-fake credentials (don't redact me, GitGuardian).
_POSITIVE = (
    "AWS_SECRET_ACCESS_KEY = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "github_token = ghp_1234567890abcdefghijklmnopqrstuvwxyzAB",
    "SECRET = sk_live_4eC39HqLyjWDarjtT1zdp7dc",
    'private_key = "-----BEGIN PRIVATE KEY-----\\nMIIEvQ...\\n-----END PRIVATE KEY-----"',
    "DATABASE_URL = 'postgres://admin:hunter2supersecret@db.example.com/prod'",
)

_NEGATIVE = (
    "What's the capital of France?",
    "Please write a haiku about autumn leaves.",
    "Convert 100 USD to EUR.",
    "Recommend a low-effort dinner recipe.",
    "Summarize this article in two paragraphs.",
    "Explain how DNS works.",
)


@pytest.fixture(scope="module")
def detector() -> SecretsDetector:
    return SecretsDetector()


@pytest.mark.parametrize("text", _POSITIVE)
async def test_positive_cases_detected(detector, text):
    result = await detector.scan(text, _CTX)
    assert result.matched is True, f"failed to detect secret in: {text!r}"
    assert result.score == 1.0
    assert result.spans


@pytest.mark.parametrize("text", _NEGATIVE)
async def test_negative_cases_clean(detector, text):
    result = await detector.scan(text, _CTX)
    assert result.matched is False, f"false positive: {text!r}"
    assert result.score == 0.0


async def test_metadata_lists_secret_types(detector):
    result = await detector.scan(
        "GITHUB_TOKEN=ghp_1234567890abcdefghijklmnopqrstuvwxyzAB",
        _CTX,
    )
    assert result.matched
    secret_types = result.metadata["secret_types"]
    assert isinstance(secret_types, list)
    assert len(secret_types) >= 1
