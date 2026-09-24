from domain.models import SandboxRouteTarget

ROUTING_MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
ROUTING_MANAGED_BY_VALUE = "sandbox-controller"
SANDBOX_HEADER = "x-sandbox-id"
BASELINE_SUBSET = "baseline"


def ready_sandbox_ids(targets: tuple[SandboxRouteTarget, ...]) -> tuple[str, ...]:
    return tuple(target.sandbox_id for target in targets if target.ready)


def build_destination_rule(service_name: str, sandbox_ids: tuple[str, ...]) -> dict:
    subsets = [{"name": BASELINE_SUBSET, "labels": {"version": BASELINE_SUBSET}}]
    subsets.extend({"name": sandbox_id, "labels": {"version": sandbox_id}} for sandbox_id in sandbox_ids)
    return {
        "apiVersion": "networking.istio.io/v1",
        "kind": "DestinationRule",
        "metadata": {
            "name": service_name,
            "labels": {ROUTING_MANAGED_BY_LABEL: ROUTING_MANAGED_BY_VALUE},
        },
        "spec": {"host": service_name, "subsets": subsets},
    }


def build_virtual_service(service_name: str, sandbox_ids: tuple[str, ...]) -> dict:
    http_routes = [_sandbox_route(service_name, sandbox_id) for sandbox_id in sandbox_ids]
    http_routes.append(_baseline_route(service_name))
    return {
        "apiVersion": "networking.istio.io/v1",
        "kind": "VirtualService",
        "metadata": {
            "name": service_name,
            "labels": {ROUTING_MANAGED_BY_LABEL: ROUTING_MANAGED_BY_VALUE},
        },
        "spec": {"hosts": [service_name], "http": http_routes},
    }


def _sandbox_route(service_name: str, sandbox_id: str) -> dict:
    return {
        "name": f"sandbox-{sandbox_id}",
        "match": [{"headers": {SANDBOX_HEADER: {"exact": sandbox_id}}}],
        "route": [{"destination": {"host": service_name, "subset": sandbox_id}}],
    }


def _baseline_route(service_name: str) -> dict:
    return {
        "name": "baseline-route",
        "route": [{"destination": {"host": service_name, "subset": BASELINE_SUBSET}}],
    }
