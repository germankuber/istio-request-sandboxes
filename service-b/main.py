import asyncio
import logging
import os

from fastapi import FastAPI

from sandbox_propagation import (
    SandboxPropagationMiddleware,
    build_client,
    current_sandbox_id,
)
from telemetry import annotate_sandbox, instrument_app, setup_telemetry

SERVICE_NAME = "B"
VERSION = os.getenv("VERSION", "baseline")
SERVICE_C_URL = os.getenv("SERVICE_C_URL", "http://service-c")
SERVICE_D_URL = os.getenv("SERVICE_D_URL", "http://service-d")
SERVICE_E_URL = os.getenv("SERVICE_E_URL", "http://service-e")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

app = FastAPI(title="service-b")
app.add_middleware(SandboxPropagationMiddleware)
instrument_app(app)


def describe(result) -> dict[str, object]:
    if isinstance(result, BaseException):
        return {"error": type(result).__name__, "detail": str(result)[:200]}
    if result.status_code >= 400:
        return {"error": f"HTTP {result.status_code}", "detail": result.text[:200]}
    return result.json()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/chain")
async def chain() -> dict[str, object]:
    sandbox_id = current_sandbox_id.get()
    annotate_sandbox(sandbox_id)
    logger.info(
        "service=%s version=%s received request sandbox_id=%s",
        SERVICE_NAME,
        VERSION,
        sandbox_id or "<none>",
    )

    async with build_client() as client:
        response_c, response_d, response_e = await asyncio.gather(
            client.get(f"{SERVICE_C_URL}/info"),
            client.get(f"{SERVICE_D_URL}/info"),
            client.get(f"{SERVICE_E_URL}/info"),
            return_exceptions=True,
        )

    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "sandbox_id": sandbox_id,
        "downstream": {
            "c": describe(response_c),
            "d": describe(response_d),
            "e": describe(response_e),
        },
    }
