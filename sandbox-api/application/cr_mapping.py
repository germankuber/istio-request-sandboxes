from application.db_preset import expand_env
from domain.sandbox import MockRequest, ServiceRequest

API_VERSION = "sandbox.poc/v1"
KIND = "Sandbox"


def build_sandbox_cr(
    name: str, services: tuple[ServiceRequest, ...], mocks: tuple[MockRequest, ...]
) -> dict:
    return {
        "apiVersion": API_VERSION,
        "kind": KIND,
        "metadata": {"name": name},
        "spec": {
            "services": [_service_to_cr(service) for service in services],
            "mocks": [_mock_to_cr(mock) for mock in mocks],
        },
    }


def _service_to_cr(service: ServiceRequest) -> dict:
    env = expand_env(service.env, service.use_migrated_db)
    entry: dict = {"name": service.name}
    if service.image:
        entry["image"] = service.image
    if env:
        entry["env"] = [{"name": item.name, "value": item.value} for item in env]
    return entry


def _mock_to_cr(mock: MockRequest) -> dict:
    entry: dict = {
        "host": mock.host,
        "method": mock.method,
        "path": mock.path,
        "status": mock.status,
        "enabled": mock.enabled,
    }
    if mock.body is not None:
        entry["body"] = mock.body
    return entry
