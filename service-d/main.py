import logging
import os

from fastapi import FastAPI, Request

from telemetry import annotate_sandbox, instrument_app, setup_telemetry

SERVICE_NAME = "D"
VERSION = os.getenv("VERSION", "baseline")
SANDBOX_HEADER = "X-Sandbox-ID"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

app = FastAPI(title="service-d")
instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/info")
def info(request: Request) -> dict[str, str]:
    sandbox_id = request.headers.get(SANDBOX_HEADER)
    annotate_sandbox(sandbox_id)
    logger.info(
        "service=%s version=%s received request sandbox_id=%s",
        SERVICE_NAME,
        VERSION,
        sandbox_id or "<none>",
    )
    return {"service": SERVICE_NAME, "version": VERSION}
