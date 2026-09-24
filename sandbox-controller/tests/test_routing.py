from domain.models import SandboxRouteTarget
from domain.routing import (
    ROUTING_MANAGED_BY_LABEL,
    ROUTING_MANAGED_BY_VALUE,
    build_destination_rule,
    build_virtual_service,
    ready_sandbox_ids,
)


def test_ready_sandbox_ids_filters_out_not_ready() -> None:
    targets = (
        SandboxRouteTarget(sandbox_id="test-123", ready=True),
        SandboxRouteTarget(sandbox_id="team-b", ready=False),
    )

    assert ready_sandbox_ids(targets) == ("test-123",)


def test_destination_rule_always_has_baseline_subset() -> None:
    dr = build_destination_rule("service-c", ())

    assert dr["metadata"]["name"] == "service-c"
    assert dr["metadata"]["labels"][ROUTING_MANAGED_BY_LABEL] == ROUTING_MANAGED_BY_VALUE
    assert dr["spec"]["host"] == "service-c"
    assert dr["spec"]["subsets"] == [{"name": "baseline", "labels": {"version": "baseline"}}]


def test_destination_rule_adds_a_subset_per_sandbox() -> None:
    dr = build_destination_rule("service-c", ("test-123", "team-c"))

    names = [subset["name"] for subset in dr["spec"]["subsets"]]
    assert names == ["baseline", "test-123", "team-c"]
    assert dr["spec"]["subsets"][1] == {"name": "test-123", "labels": {"version": "test-123"}}


def test_virtual_service_always_has_baseline_route_last() -> None:
    vs = build_virtual_service("service-c", ())

    assert vs["spec"]["hosts"] == ["service-c"]
    assert vs["spec"]["http"] == [
        {"name": "baseline-route", "route": [{"destination": {"host": "service-c", "subset": "baseline"}}]}
    ]


def test_virtual_service_adds_exact_header_route_per_sandbox_before_baseline() -> None:
    vs = build_virtual_service("service-c", ("test-123", "team-c"))

    route_names = [route["name"] for route in vs["spec"]["http"]]
    assert route_names == ["sandbox-test-123", "sandbox-team-c", "baseline-route"]

    first_route = vs["spec"]["http"][0]
    assert first_route["match"] == [{"headers": {"x-sandbox-id": {"exact": "test-123"}}}]
    assert first_route["route"] == [{"destination": {"host": "service-c", "subset": "test-123"}}]


def test_virtual_service_two_sandboxes_on_same_service_both_get_routes() -> None:
    vs = build_virtual_service("service-c", ("test-123", "team-c"))

    matches = {route["name"]: route["match"][0]["headers"]["x-sandbox-id"]["exact"] for route in vs["spec"]["http"][:-1]}
    assert matches == {"sandbox-test-123": "test-123", "sandbox-team-c": "team-c"}
