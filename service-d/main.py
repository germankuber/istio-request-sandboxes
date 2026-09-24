import asyncio
import logging
import os

import httpx
from fastapi import FastAPI

from sandbox_propagation import SandboxPropagationMiddleware, build_client, current_sandbox_id
from telemetry import annotate_sandbox, instrument_app, setup_telemetry

SERVICE_NAME = "D"
VERSION = os.getenv("VERSION", "baseline")
EXTERNAL_PAYMENTS_URL = os.getenv(
    "EXTERNAL_PAYMENTS_URL", "http://external-payments.external.svc.cluster.local"
)
EXTERNAL_WEATHER_URL = os.getenv(
    "EXTERNAL_WEATHER_URL", "http://external-weather.external.svc.cluster.local"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

app = FastAPI(title="service-d")
app.add_middleware(SandboxPropagationMiddleware)
instrument_app(app)


def describe_external(result: httpx.Response | BaseException) -> dict[str, object]:
    if isinstance(result, BaseException):
        return {"error": type(result).__name__, "detail": str(result)[:200], "mocked": False}
    try:
        body = result.json()
    except ValueError:
        body = {"raw": result.text[:200]}
    return {
        "http_status": result.status_code,
        "mocked": result.headers.get("X-Mock", "").lower() == "true",
        "data": body,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/info")
async def info() -> dict[str, object]:
    sandbox_id = current_sandbox_id.get()
    annotate_sandbox(sandbox_id)
    logger.info(
        "service=%s version=%s received request sandbox_id=%s",
        SERVICE_NAME,
        VERSION,
        sandbox_id or "<none>",
    )

    async with build_client() as client:
        payments_result, weather_result = await asyncio.gather(
            client.post(
                f"{EXTERNAL_PAYMENTS_URL}/charge",
                json={"amount_cents": 1999, "currency": "USD"},
            ),
            client.get(f"{EXTERNAL_WEATHER_URL}/weather", params={"city": "Buenos Aires"}),
            return_exceptions=True,
        )

    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "external": {
            "payments": describe_external(payments_result),
            "weather": describe_external(weather_result),
        },
    }
