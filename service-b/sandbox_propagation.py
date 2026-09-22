from contextvars import ContextVar

import httpx
from starlette.middleware.base import BaseHTTPMiddleware

SANDBOX_HEADER = "X-Sandbox-ID"

current_sandbox_id: ContextVar[str | None] = ContextVar("current_sandbox_id", default=None)


class SandboxPropagationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = current_sandbox_id.set(request.headers.get(SANDBOX_HEADER))
        try:
            return await call_next(request)
        finally:
            current_sandbox_id.reset(token)


async def inject_sandbox_header(request: httpx.Request) -> None:
    sandbox_id = current_sandbox_id.get()
    if sandbox_id is not None:
        request.headers[SANDBOX_HEADER] = sandbox_id


def build_client(timeout: float = 5.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        event_hooks={"request": [inject_sandbox_header]},
    )
