import asyncio
import logging
import os
from typing import Any, Callable, cast

import kopf

from application.deployment_service import DeploymentService
from application.mock_service import MockService
from application.routing_service import RoutingService
from application.sandbox_lifecycle import handle_delete, handle_reconcile
from application.spec_parsing import parse_sandbox
from infrastructure.k8s_gateway import K8sGateway
from infrastructure.mock_manager_gateway import MockManagerGateway

NAMESPACE = os.getenv("SANDBOX_NAMESPACE", "default")
MOCK_MANAGER_URL = os.getenv("MOCK_MANAGER_URL", "http://mock-manager")
ROUTING_INTERVAL_SECONDS = float(os.getenv("ROUTING_INTERVAL_SECONDS", "10"))
NOT_READY_RETRY_SECONDS = float(os.getenv("NOT_READY_RETRY_SECONDS", "5"))
ERROR_RETRY_SECONDS = float(os.getenv("ERROR_RETRY_SECONDS", "10"))
MOCK_GC_INTERVAL_SECONDS = float(os.getenv("MOCK_GC_INTERVAL_SECONDS", "30"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sandbox-controller")

k8s_gateway = K8sGateway(NAMESPACE)
mock_gateway = MockManagerGateway(MOCK_MANAGER_URL)

deployment_service = DeploymentService(k8s_gateway)
routing_service = RoutingService(k8s_gateway)
mock_service = MockService(mock_gateway)

_ChangingDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]
_ActivityDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]


@cast(_ChangingDecorator, kopf.on.create("sandbox.poc", "v1", "sandboxes"))
@cast(_ChangingDecorator, kopf.on.update("sandbox.poc", "v1", "sandboxes"))
def reconcile_sandbox(spec: dict, name: str, uid: str, patch: kopf.Patch, **_: object) -> None:
    sandbox = parse_sandbox(name, spec, uid=uid)
    handle_reconcile(
        sandbox,
        deployment_service,
        mock_service,
        routing_service,
        patch,
        error_retry_seconds=ERROR_RETRY_SECONDS,
        not_ready_retry_seconds=NOT_READY_RETRY_SECONDS,
    )


@cast(_ChangingDecorator, kopf.on.delete("sandbox.poc", "v1", "sandboxes"))
def delete_sandbox(spec: dict, name: str, **_: object) -> None:
    sandbox = parse_sandbox(name, spec)
    handle_delete(sandbox, mock_service, routing_service, logger)


@cast(_ActivityDecorator, kopf.on.startup())
async def start_periodic_routing_reconcile(**_: object) -> None:
    asyncio.create_task(_periodic_routing_reconcile())
    asyncio.create_task(_periodic_mock_gc())


async def _periodic_routing_reconcile() -> None:
    while True:
        await asyncio.sleep(ROUTING_INTERVAL_SECONDS)
        try:
            service_names = await asyncio.to_thread(k8s_gateway.known_service_names)
            await asyncio.to_thread(routing_service.reconcile_services, service_names)
        except Exception:
            logger.exception("periodic routing reconcile failed")


async def _periodic_mock_gc() -> None:
    while True:
        await asyncio.sleep(MOCK_GC_INTERVAL_SECONDS)
        try:
            deleted = await asyncio.to_thread(mock_service.collect_orphans, k8s_gateway.known_sandbox_ids, logger)
            if deleted:
                logger.info("mock GC swept %d orphaned rule(s): %s", len(deleted), deleted)
        except Exception:
            logger.exception("periodic mock rule GC failed")
