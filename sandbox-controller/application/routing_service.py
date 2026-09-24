from domain.ports import RoutingGateway
from domain.routing import build_destination_rule, build_virtual_service, ready_sandbox_ids


class RoutingService:
    def __init__(self, gateway: RoutingGateway) -> None:
        self._gateway = gateway

    def reconcile_service(self, service_name: str) -> None:
        targets = self._gateway.route_targets(service_name)
        sandbox_ids = ready_sandbox_ids(targets)

        if not sandbox_ids:
            self._gateway.delete_virtual_service(service_name)
            self._gateway.delete_destination_rule(service_name)
            return

        self._gateway.apply_destination_rule(build_destination_rule(service_name, sandbox_ids))
        self._gateway.apply_virtual_service(build_virtual_service(service_name, sandbox_ids))

    def reconcile_services(self, service_names: set[str]) -> None:
        for service_name in service_names:
            self.reconcile_service(service_name)
