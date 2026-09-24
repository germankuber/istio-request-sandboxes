import logging

import kopf
import pytest

from application.deployment_service import DeploymentService
from application.mock_service import MockService
from application.routing_service import RoutingService
from application.sandbox_lifecycle import handle_delete, handle_reconcile
from domain.models import Sandbox, ServiceOverride
from tests.conftest import FakeDeploymentGateway, FakeMockGateway, FakeRoutingGateway

BASELINE = {
    "spec": {
        "template": {
            "spec": {"containers": [{"name": "service-c", "image": "service-c:latest", "env": []}]},
        }
    }
}


class RaisingMockGateway:
    def list_rules(self, sandbox_id: str) -> tuple:
        raise RuntimeError("mock-manager unreachable")

    def list_all_rules(self) -> tuple:
        raise AssertionError("should not be called")

    def create_rule(self, sandbox_id: str, mock: object) -> None:
        raise AssertionError("should not be called")

    def delete_rule(self, rule_id: str) -> None:
        raise AssertionError("should not be called")


class RecordingRoutingGateway(FakeRoutingGateway):
    def __init__(self) -> None:
        super().__init__()
        self.route_targets_calls: list[str] = []

    def route_targets(self, service_name: str) -> tuple:
        self.route_targets_calls.append(service_name)
        return super().route_targets(service_name)


def test_handle_delete_reconciles_routing_even_when_mock_cleanup_fails(caplog: pytest.LogCaptureFixture) -> None:
    sandbox = Sandbox(sandbox_id="test-123", services=(ServiceOverride(name="service-c"),), mocks=())
    mock_service = MockService(RaisingMockGateway())
    routing_gateway = RecordingRoutingGateway()
    routing_service = RoutingService(routing_gateway)
    logger = logging.getLogger("test-handle-delete")

    with caplog.at_level(logging.WARNING, logger="test-handle-delete"):
        handle_delete(sandbox, mock_service, routing_service, logger)

    assert routing_gateway.route_targets_calls == ["service-c"]
    assert "test-123" in caplog.text


def test_handle_reconcile_routes_removed_service_before_deleting_its_deployment() -> None:
    events: list[tuple[str, str]] = []

    class RecordingDeploymentGateway(FakeDeploymentGateway):
        def delete_sandbox_deployment(self, service_name: str, sandbox_id: str) -> None:
            events.append(("delete_deployment", service_name))
            super().delete_sandbox_deployment(service_name, sandbox_id)

    class RecordingRoutingForReconcile(FakeRoutingGateway):
        def route_targets(self, service_name: str) -> tuple:
            events.append(("route_targets", service_name))
            return super().route_targets(service_name)

    deployment_gateway = RecordingDeploymentGateway({"service-c": BASELINE})
    deployment_gateway.applied[("service-c", "test-123")] = {}
    deployment_gateway.applied[("service-d", "test-123")] = {}

    sandbox = Sandbox(sandbox_id="test-123", services=(ServiceOverride(name="service-c"),), mocks=())
    deployment_service = DeploymentService(deployment_gateway)
    mock_service = MockService(FakeMockGateway())
    routing_gateway = RecordingRoutingForReconcile()
    routing_service = RoutingService(routing_gateway)
    patch = kopf.Patch()

    with pytest.raises(kopf.TemporaryError):
        handle_reconcile(
            sandbox,
            deployment_service,
            mock_service,
            routing_service,
            patch,
            error_retry_seconds=1.0,
            not_ready_retry_seconds=1.0,
        )

    assert events[0] == ("route_targets", "service-d")
    assert events[1] == ("delete_deployment", "service-d")
    final_pass = events[2:]
    assert ("route_targets", "service-c") in final_pass
    assert ("route_targets", "service-d") in final_pass


def test_handle_reconcile_sets_failed_status_and_raises_temporary_error_on_exception() -> None:
    deployment_gateway = FakeDeploymentGateway({})
    sandbox = Sandbox(sandbox_id="test-123", services=(ServiceOverride(name="service-c"),), mocks=())
    deployment_service = DeploymentService(deployment_gateway)
    mock_service = MockService(FakeMockGateway())
    routing_service = RoutingService(FakeRoutingGateway())
    patch = kopf.Patch()

    with pytest.raises(kopf.TemporaryError) as exc_info:
        handle_reconcile(
            sandbox,
            deployment_service,
            mock_service,
            routing_service,
            patch,
            error_retry_seconds=7.0,
            not_ready_retry_seconds=1.0,
        )

    assert patch.status["phase"] == "Failed"
    assert exc_info.value.delay == 7.0
