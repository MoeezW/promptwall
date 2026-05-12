"""Server entry point.

On Windows, ``psycopg``'s async mode requires ``WindowsSelectorEventLoopPolicy``
and refuses ``ProactorEventLoop``. ``uvicorn.run()`` rewrites the policy
internally on Windows, so we drive the server through ``asyncio.run`` instead —
that way our policy is what's in effect when the event loop is created.
"""

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000


def main() -> None:
    """Run the proxy."""
    config = uvicorn.Config(
        "promptwall.proxy:app",
        host=_DEFAULT_HOST,
        port=_DEFAULT_PORT,
        log_config=None,
    )
    server = uvicorn.Server(config=config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
