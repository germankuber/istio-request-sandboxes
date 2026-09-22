import logging
import os

from fastapi import FastAPI, Request

from telemetry import annotate_sandbox, instrument_app, setup_telemetry

SERVICE_NAME = "C"
VERSION = os.getenv("VERSION", "baseline")
SANDBOX_HEADER = "X-Sandbox-ID"

setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

from products import fetch_products_legacy, fetch_products_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)


app = FastAPI(title="service-c")
instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/info")
def info(request: Request) -> dict[str, object]:
    sandbox_id = request.headers.get(SANDBOX_HEADER)
    annotate_sandbox(sandbox_id)

    if VERSION == "sandbox":
        products = [
            {
                "id": row["id"],
                "brand": row["brand"],
                "model": row["model"],
                "price_cents": row["price_cents"],
                "stock": row["stock"],
            }
            for row in fetch_products_split()
        ]
        schema = "brand+model"
    else:
        products = [
            {
                "id": row["id"],
                "name": row["name"],
                "price_cents": row["price_cents"],
                "stock": row["stock"],
            }
            for row in fetch_products_legacy()
        ]
        schema = "name"

    logger.info(
        "service=%s version=%s schema=%s products=%d sandbox_id=%s",
        SERVICE_NAME,
        VERSION,
        schema,
        len(products),
        sandbox_id or "<none>",
    )

    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "schema": schema,
        "products": products,
    }
