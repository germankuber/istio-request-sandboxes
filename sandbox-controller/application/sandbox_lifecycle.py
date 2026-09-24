import logging

import kopf

from application.deployment_service import DeploymentService
from application.mock_service import MockService
from application.routing_service import RoutingService
from domain.models import Sandbox

DELETE_MOCK_CLEANUP_WARNING = "mock cleanup failed for sandbox %s, continuing with routing teardown"
RECONCILE_WAITING_MESSAGE = "waiting for sandboxed deployments to become ready"


def handle_delete(
    sandbox: Sandbox,
    mock_service: MockService,
    routing_service: RoutingService,
    logger: logging.Logger,
) -> None:
    try:
        mock_service.delete_all(sandbox.sandbox_id)
    except Exception:
        logger.warning(DELETE_MOCK_CLEANUP_WARNING, sandbox.sandbox_id, exc_info=True)

    routing_service.reconcile_services(set(sandbox.service_names()))


def handle_reconcile(
    sandbox: Sandbox,
    deployment_service: DeploymentService,
    mock_service: MockService,
    routing_service: RoutingService,
    patch: kopf.Patch,
    error_retry_seconds: float,
    not_ready_retry_seconds: float,
) -> None:
    desired_service_names = set(sandbox.service_names())

    try:
        previously_managed = set(deployment_service.managed_service_names(sandbox.sandbox_id))
        removed_service_names = previously_managed - desired_service_names
        routing_service.reconcile_services(removed_service_names)

        deployment_service.reconcile(sandbox)
        mock_service.seed(sandbox)
    except Exception as error:
        patch.status["phase"] = "Failed"
        patch.status["message"] = str(error)
        raise kopf.TemporaryError(str(error), delay=error_retry_seconds) from error

    routing_service.reconcile_services(previously_managed | desired_service_names)

    _patch_readiness_status(sandbox, deployment_service, patch, not_ready_retry_seconds)


def _patch_readiness_status(
    sandbox: Sandbox,
    deployment_service: DeploymentService,
    patch: kopf.Patch,
    not_ready_retry_seconds: float,
) -> None:
    readiness = deployment_service.service_readiness(sandbox)
    patch.status["services"] = [{"name": svc, "ready": ready} for svc, ready in readiness.items()]

    if all(readiness.values()):
        patch.status["phase"] = "Ready"
        patch.status["message"] = "all sandboxed services available"
        return

    patch.status["phase"] = "Pending"
    patch.status["message"] = RECONCILE_WAITING_MESSAGE
    raise kopf.TemporaryError(RECONCILE_WAITING_MESSAGE, delay=not_ready_retry_seconds)
