"""OpenAI provider — async forwarder backed by httpx.

The adapter owns a persistent ``httpx.AsyncClient`` with a connection pool;
construct it once at startup (lifespan), close it once at shutdown. A
caller-provided client is honoured for tests so respx can mock without
intercepting the production pool.
"""

from collections.abc import Mapping

import httpx

from promptwall.settings import Settings

_CHAT_COMPLETIONS_PATH = "/chat/completions"
_MAX_CONNECTIONS = 100
_MAX_KEEPALIVE = 20


class OpenAIAdapter:
    """Forward chat-completion requests to api.openai.com."""

    name = "openai"

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.openai_base_url,
            timeout=settings.openai_timeout_seconds,
            limits=httpx.Limits(
                max_connections=_MAX_CONNECTIONS,
                max_keepalive_connections=_MAX_KEEPALIVE,
            ),
        )

    async def aclose(self) -> None:
        """Close the owned httpx client. No-op for caller-supplied clients."""
        if self._owns_client:
            await self._client.aclose()

    async def forward(self, payload: Mapping[str, object]) -> httpx.Response:
        """Post ``payload`` to OpenAI and return the raw response."""
        return await self._client.post(
            _CHAT_COMPLETIONS_PATH,
            json=payload,
            headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
        )
