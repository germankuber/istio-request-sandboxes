import logging
import uuid

from fastapi import FastAPI
from pydantic import BaseModel, Field

SERVICE_NAME = "external-payments"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)


class ChargeRequest(BaseModel):
    amount_cents: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class ChargeResponse(BaseModel):
    status: str
    charge_id: str
    amount_cents: int
    provider: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/charge", response_model=ChargeResponse)
def charge(request: ChargeRequest) -> ChargeResponse:
    logger.info(
        "charge amount_cents=%s currency=%s", request.amount_cents, request.currency
    )
    return ChargeResponse(
        status="approved",
        charge_id=f"ch_{uuid.uuid4().hex[:16]}",
        amount_cents=request.amount_cents,
        provider=SERVICE_NAME,
    )
