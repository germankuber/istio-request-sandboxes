from application.deployment_service import DeploymentService
from domain.models import Sandbox, ServiceOverride
from tests.conftest import FakeDeploymentGateway

BASELINE = {
    "spec": {
        "template": {
            "spec": {"containers": [{"name": "service-c", "image": "service-c:latest", "env": []}]},
        }
    }
}


def test_reconcile_applies_a_deployment_per_service() -> None:
    gateway = FakeDeploymentGateway({"service-c": BASELINE, "service-e": BASELINE})
    sandbox = Sandbox(
        sandbox_id="test-123",
        services=(ServiceOverride(name="service-c"), ServiceOverride(name="service-e")),
        mocks=(),
    )

    DeploymentService(gateway).reconcile(sandbox)

    assert set(gateway.applied.keys()) == {("service-c", "test-123"), ("service-e", "test-123")}


def test_reconcile_removes_deployments_for_services_dropped_from_spec() -> None:
    gateway = FakeDeploymentGateway({"service-c": BASELINE})
    sandbox = Sandbox(sandbox_id="test-123", services=(ServiceOverride(name="service-c"),), mocks=())
    service = DeploymentService(gateway)
    service.reconcile(sandbox)

    narrowed_sandbox = Sandbox(sandbox_id="test-123", services=(), mocks=())
    service.reconcile(narrowed_sandbox)

    assert gateway.applied == {}
    assert ("service-c", "test-123") in gateway.deleted


def test_all_ready_true_only_when_every_service_deployment_is_ready() -> None:
    gateway = FakeDeploymentGateway()
    gateway.ready = {("service-c", "test-123")}
    sandbox = Sandbox(
        sandbox_id="test-123",
        services=(ServiceOverride(name="service-c"), ServiceOverride(name="service-e")),
        mocks=(),
    )

    assert DeploymentService(gateway).all_ready(sandbox) is False

    gateway.ready.add(("service-e", "test-123"))
    assert DeploymentService(gateway).all_ready(sandbox) is True


def test_service_readiness_reports_per_service_status() -> None:
    gateway = FakeDeploymentGateway()
    gateway.ready = {("service-c", "test-123")}
    sandbox = Sandbox(
        sandbox_id="test-123",
        services=(ServiceOverride(name="service-c"), ServiceOverride(name="service-e")),
        mocks=(),
    )

    assert DeploymentService(gateway).service_readiness(sandbox) == {"service-c": True, "service-e": False}
