import logging

from fastapi import FastAPI, Query

SERVICE_NAME = "external-weather"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title=SERVICE_NAME)

CONDITIONS = ["clear", "clouds", "rain", "storm"]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.get("/weather")
def weather(city: str = Query(...)) -> dict[str, object]:
    logger.info("weather city=%s", city)
    fingerprint = sum(ord(character) for character in city)
    temp_c = 15 + (fingerprint % 20)
    condition = CONDITIONS[fingerprint % len(CONDITIONS)]
    return {
        "city": city,
        "temp_c": temp_c,
        "condition": condition,
        "provider": SERVICE_NAME,
    }
