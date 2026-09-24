from domain.deployment import build_sandbox_deployment
from domain.models import Sandbox
from domain.ports import DeploymentGateway


class DeploymentService:
    def __init__(self, gateway: DeploymentGateway) -> None:
        self._gateway = gateway

    def managed_service_names(self, sandbox_id: str) -> tuple[str, ...]:
        return self._gateway.list_managed_service_names(sandbox_id)

    def reconcile(self, sandbox: Sandbox) -> None:
        desired_names = set(sandbox.service_names())
        existing_names = set(self._gateway.list_managed_service_names(sandbox.sandbox_id))

        for service in sandbox.services:
            baseline = self._gateway.get_baseline(service.name)
            manifest = build_sandbox_deployment(baseline, sandbox, service)
            self._gateway.apply_sandbox_deployment(manifest, sandbox)

        for stale_service_name in existing_names - desired_names:
            self._gateway.delete_sandbox_deployment(stale_service_name, sandbox.sandbox_id)

    def service_readiness(self, sandbox: Sandbox) -> dict[str, bool]:
        return {
            service.name: self._gateway.is_ready(service.name, sandbox.sandbox_id) for service in sandbox.services
        }

    def all_ready(self, sandbox: Sandbox) -> bool:
        readiness = self.service_readiness(sandbox)
        return all(readiness.values()) if readiness else True
