import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sandbox_propagation import (
    SandboxPropagationMiddleware,
    build_client,
    current_sandbox_id,
)
from telemetry import annotate_sandbox, instrument_app, setup_telemetry

SERVICE_NAME = "A"
VERSION = os.getenv("VERSION", "baseline")
SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

app = FastAPI(title="service-a")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)
app.add_middleware(SandboxPropagationMiddleware)
instrument_app(app)


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
        response = await client.get(f"{SERVICE_B_URL}/chain")
        downstream = response.json()

    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "sandbox_id": sandbox_id,
        "downstream": downstream,
    }
