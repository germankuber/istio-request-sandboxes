from application.cr_mapping import build_sandbox_cr
from application.name_validation import validate_sandbox_name
from application.service_catalog import sandboxable_services
from domain.errors import SandboxAlreadyExistsError, SandboxNotFoundError
from domain.ports import SandboxPort
from domain.sandbox import MockRequest, SandboxSummary, ServiceInfo, ServiceRequest


class SandboxService:
    def __init__(self, port: SandboxPort) -> None:
        self._port = port

    def list_sandboxes(self) -> list[SandboxSummary]:
        return [_to_summary(item) for item in self._port.list_sandboxes()]

    def get_sandbox(self, name: str) -> dict:
        sandbox = self._port.get_sandbox(name)
        if sandbox is None:
            raise SandboxNotFoundError(name)
        return sandbox

    def create_sandbox(
        self, name: str, services: tuple[ServiceRequest, ...], mocks: tuple[MockRequest, ...]
    ) -> dict:
        validate_sandbox_name(name)
        if self._port.get_sandbox(name) is not None:
            raise SandboxAlreadyExistsError(name)
        body = build_sandbox_cr(name, services, mocks)
        return self._port.create_sandbox(body)

    def delete_sandbox(self, name: str) -> None:
        if self._port.get_sandbox(name) is None:
            raise SandboxNotFoundError(name)
        self._port.delete_sandbox(name)

    def list_services(self) -> list[ServiceInfo]:
        return sandboxable_services(self._port.list_baseline_deployments())


DELETING_PHASE = "Deleting"
DELETING_MESSAGE = "cleaning up deployments, routes and mocks"


def _to_summary(item: dict) -> SandboxSummary:
    metadata = item.get("metadata", {})
    spec = item.get("spec", {})
    status = item.get("status", {})
    is_deleting = metadata.get("deletionTimestamp") is not None
    return SandboxSummary(
        name=metadata.get("name", ""),
        phase=DELETING_PHASE if is_deleting else status.get("phase", "Pending"),
        message=DELETING_MESSAGE if is_deleting else status.get("message", ""),
        service_names=tuple(entry["name"] for entry in spec.get("services", [])),
        mocks_count=len(spec.get("mocks", [])),
        created_at=metadata.get("creationTimestamp"),
    )
