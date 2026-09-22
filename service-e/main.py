import logging
import os

from fastapi import FastAPI, Request

from telemetry import annotate_sandbox, instrument_app, setup_telemetry

SERVICE_NAME = "E"
VERSION = os.getenv("VERSION", "baseline")
SANDBOX_HEADER = "X-Sandbox-ID"
LOW_STOCK_THRESHOLD = 15

setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

from products import fetch_products_legacy, fetch_products_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)


app = FastAPI(title="service-e")
instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "version": VERSION}


@app.get("/info")
def info(request: Request) -> dict[str, object]:
    sandbox_id = request.headers.get(SANDBOX_HEADER)
    annotate_sandbox(sandbox_id)

    if VERSION == "sandbox":
        rows = fetch_products_split()
        products = [{**row, "name": f"{row['brand']} {row['model']}"} for row in rows]
    else:
        products = fetch_products_legacy()

    low_stock = [
        {"id": row["id"], "name": row["name"], "stock": row["stock"]}
        for row in products
        if row["stock"] < LOW_STOCK_THRESHOLD
    ]
    inventory_value_cents = sum(row["price_cents"] * row["stock"] for row in products)

    logger.info(
        "service=%s version=%s products=%d low_stock=%d sandbox_id=%s",
        SERVICE_NAME,
        VERSION,
        len(products),
        len(low_stock),
        sandbox_id or "<none>",
    )

    return {
        "service": SERVICE_NAME,
        "version": VERSION,
        "product_count": len(products),
        "inventory_value_cents": inventory_value_cents,
        "low_stock": low_stock,
    }
