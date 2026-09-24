from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnvVar:
    name: str
    value: str


@dataclass(frozen=True, slots=True)
class ServiceRequest:
    name: str
    image: str | None
    env: tuple[EnvVar, ...]
    use_migrated_db: bool


@dataclass(frozen=True, slots=True)
class MockRequest:
    host: str
    method: str
    path: str
    status: int
    body: object
    enabled: bool


@dataclass(frozen=True, slots=True)
class SandboxSummary:
    name: str
    phase: str
    message: str
    service_names: tuple[str, ...]
    mocks_count: int
    created_at: str | None


@dataclass(frozen=True, slots=True)
class ServiceInfo:
    name: str
    uses_db: bool


@dataclass(frozen=True, slots=True)
class BaselineDeployment:
    app: str
    version: str | None
    env: dict[str, str]
