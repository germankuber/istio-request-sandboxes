from domain.models import EnvOverride, MockRuleSpec, Sandbox, ServiceOverride


def parse_sandbox(name: str, spec: dict, uid: str | None = None) -> Sandbox:
    services = tuple(_parse_service(entry) for entry in spec.get("services", []))
    mocks = tuple(_parse_mock(entry) for entry in spec.get("mocks", []))
    return Sandbox(sandbox_id=name, services=services, mocks=mocks, uid=uid)


def _parse_service(entry: dict) -> ServiceOverride:
    env = tuple(EnvOverride(name=item["name"], value=item["value"]) for item in entry.get("env", []))
    return ServiceOverride(name=entry["name"], image=entry.get("image"), env=env)


def _parse_mock(entry: dict) -> MockRuleSpec:
    return MockRuleSpec(
        host=entry["host"],
        method=entry["method"],
        path=entry["path"],
        status=entry["status"],
        body=entry.get("body"),
        enabled=entry.get("enabled", True),
    )
