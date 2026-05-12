import httpx
import respx

from promptwall.providers.openai import OpenAIAdapter
from promptwall.settings import Settings


async def test_adapter_forwards_payload_with_bearer_token():
    settings = Settings()
    adapter = OpenAIAdapter(settings)
    try:
        with respx.mock:
            route = respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(200, json={"id": "stub-id"})
            )
            response = await adapter.forward({"model": "gpt-4o-mini", "messages": []})
        assert response.status_code == 200
        assert response.json()["id"] == "stub-id"
        assert route.called
        sent = route.calls[0].request
        assert sent.headers["authorization"] == "Bearer test"
    finally:
        await adapter.aclose()


async def test_adapter_returns_raw_response_on_error_status():
    settings = Settings()
    adapter = OpenAIAdapter(settings)
    try:
        with respx.mock:
            respx.post("https://api.openai.com/v1/chat/completions").mock(
                return_value=httpx.Response(429, json={"error": {"message": "rate limited"}})
            )
            response = await adapter.forward({"model": "x", "messages": []})
        assert response.status_code == 429
        assert response.json()["error"]["message"] == "rate limited"
    finally:
        await adapter.aclose()
