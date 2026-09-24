from pydantic import BaseModel, Field, field_validator, model_validator

from application.env_validation import validate_env_var_name
from application.image_validation import validate_service_image
from application.name_validation import validate_sandbox_name
from domain.sandbox import EnvVar, MockRequest, ServiceInfo, ServiceRequest


class EnvVarRequest(BaseModel):
    name: str = Field(min_length=1)
    value: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        validate_env_var_name(value)
        return value


class ServiceCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    image: str | None = None
    env: list[EnvVarRequest] = Field(default_factory=list)
    use_migrated_db: bool = False

    @model_validator(mode="after")
    def _validate_image(self) -> "ServiceCreateRequest":
        if self.image is not None:
            validate_service_image(self.name, self.image)
        return self

    def to_domain(self) -> ServiceRequest:
        return ServiceRequest(
            name=self.name,
            image=self.image,
            env=tuple(EnvVar(name=item.name, value=item.value) for item in self.env),
            use_migrated_db=self.use_migrated_db,
        )


class MockCreateRequest(BaseModel):
    host: str = Field(min_length=1)
    method: str = Field(min_length=1)
    path: str = Field(min_length=1)
    status: int = Field(ge=100, le=599)
    body: object = None
    enabled: bool = True

    def to_domain(self) -> MockRequest:
        return MockRequest(
            host=self.host,
            method=self.method.upper(),
            path=self.path,
            status=self.status,
            body=self.body,
            enabled=self.enabled,
        )


class SandboxCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    services: list[ServiceCreateRequest] = Field(default_factory=list)
    mocks: list[MockCreateRequest] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        validate_sandbox_name(value)
        return value


class SandboxSummaryResponse(BaseModel):
    name: str
    phase: str
    message: str
    services: list[str]
    mocks_count: int
    created_at: str | None


class SandboxDetailResponse(BaseModel):
    name: str
    spec: dict
    status: dict


class ServiceInfoResponse(BaseModel):
    name: str
    uses_db: bool

    @staticmethod
    def from_domain(info: ServiceInfo) -> "ServiceInfoResponse":
        return ServiceInfoResponse(name=info.name, uses_db=info.uses_db)
