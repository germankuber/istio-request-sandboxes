import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes import router
from application.reconciler import Reconciler
from application.rule_service import RuleService
from infrastructure.sqlite_repository import SqliteRuleRepository
from infrastructure.wiremock_adapter import WireMockAdapter
from telemetry import instrument_app, setup_telemetry

SERVICE_NAME = "mock-manager"
VERSION = os.getenv("VERSION", "baseline")
DB_PATH = os.getenv("MOCK_MANAGER_DB_PATH", "/data/mock-manager.db")
WIREMOCK_ADMIN_URL = os.getenv("WIREMOCK_ADMIN_URL", "http://mock-proxy/__admin")
RECONCILE_INTERVAL_SECONDS = float(os.getenv("RECONCILE_INTERVAL_SECONDS", "15"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(SERVICE_NAME)

setup_telemetry(SERVICE_NAME, VERSION)

repository = SqliteRuleRepository(DB_PATH)
stub_store = WireMockAdapter(WIREMOCK_ADMIN_URL)
reconciler = Reconciler(repository, stub_store)
rule_service = RuleService(repository, reconciler)


async def periodic_reconcile() -> None:
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL_SECONDS)
        try:
            result = await asyncio.to_thread(reconciler.reconcile)
            if result.upserted or result.removed or result.failed:
                logger.info(
                    "periodic reconcile upserted=%s removed=%s failed=%s",
                    result.upserted,
                    result.removed,
                    result.failed,
                )
        except Exception:
            logger.exception("periodic reconcile failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        await asyncio.to_thread(reconciler.reconcile)
    except Exception:
        logger.exception("startup reconcile failed")

    task = asyncio.create_task(periodic_reconcile())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title=SERVICE_NAME, lifespan=lifespan)
app.state.rule_service = rule_service
app.include_router(router)
instrument_app(app)
