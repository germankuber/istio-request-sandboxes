from application.routing_service import RoutingService
from domain.models import SandboxRouteTarget
from tests.conftest import FakeRoutingGateway


def test_reconcile_service_with_no_ready_targets_deletes_managed_routing() -> None:
    gateway = FakeRoutingGateway({"service-c": (SandboxRouteTarget(sandbox_id="test-123", ready=False),)})
    gateway.destination_rules["service-c"] = {"stale": True}
    gateway.virtual_services["service-c"] = {"stale": True}

    RoutingService(gateway).reconcile_service("service-c")

    assert "service-c" not in gateway.destination_rules
    assert "service-c" not in gateway.virtual_services


def test_reconcile_service_applies_dr_and_vs_for_ready_targets() -> None:
    gateway = FakeRoutingGateway({"service-c": (SandboxRouteTarget(sandbox_id="test-123", ready=True),)})

    RoutingService(gateway).reconcile_service("service-c")

    assert gateway.destination_rules["service-c"]["spec"]["subsets"][-1]["name"] == "test-123"
    assert gateway.virtual_services["service-c"]["spec"]["http"][0]["name"] == "sandbox-test-123"


def test_reconcile_service_two_ready_sandboxes_both_get_a_route() -> None:
    gateway = FakeRoutingGateway(
        {
            "service-c": (
                SandboxRouteTarget(sandbox_id="test-123", ready=True),
                SandboxRouteTarget(sandbox_id="team-c", ready=True),
            )
        }
    )

    RoutingService(gateway).reconcile_service("service-c")

    route_names = [route["name"] for route in gateway.virtual_services["service-c"]["spec"]["http"]]
    assert route_names == ["sandbox-test-123", "sandbox-team-c", "baseline-route"]


def test_reconcile_services_iterates_every_service_name() -> None:
    gateway = FakeRoutingGateway(
        {
            "service-c": (SandboxRouteTarget(sandbox_id="test-123", ready=True),),
            "service-d": (SandboxRouteTarget(sandbox_id="team-b", ready=True),),
        }
    )

    RoutingService(gateway).reconcile_services({"service-c", "service-d"})

    assert set(gateway.destination_rules.keys()) == {"service-c", "service-d"}
