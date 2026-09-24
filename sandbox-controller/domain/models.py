from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EnvOverride:
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class ServiceOverride:
    name: str
    image: str | None = None
    env: tuple[EnvOverride, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class MockRuleSpec:
    host: str
    method: str
    path: str
    status: int
    body: object
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class Sandbox:
    sandbox_id: str
    services: tuple[ServiceOverride, ...]
    mocks: tuple[MockRuleSpec, ...]
    uid: str | None = None

    def service_names(self) -> tuple[str, ...]:
        return tuple(service.name for service in self.services)

    def service(self, name: str) -> ServiceOverride | None:
        for service in self.services:
            if service.name == name:
                return service
        return None


@dataclass(frozen=True, slots=True)
class SandboxRouteTarget:
    sandbox_id: str
    ready: bool
