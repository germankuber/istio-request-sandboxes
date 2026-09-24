from pydantic import BaseModel, ConfigDict, Field

from domain.rule import ExternalHost, Rule, RuleBody


class RuleCreateRequest(BaseModel):
    sandbox_id: str = Field(min_length=1)
    host: ExternalHost
    method: str = Field(min_length=1)
    path: str = Field(min_length=1)
    status: int = Field(ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: RuleBody = None
    delay_ms: int = Field(default=0, ge=0)
    enabled: bool = True


class RuleUpdateRequest(BaseModel):
    sandbox_id: str | None = Field(default=None, min_length=1)
    host: ExternalHost | None = None
    method: str | None = Field(default=None, min_length=1)
    path: str | None = Field(default=None, min_length=1)
    status: int | None = Field(default=None, ge=100, le=599)
    headers: dict[str, str] | None = None
    body: RuleBody = None
    delay_ms: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sandbox_id: str
    host: ExternalHost
    method: str
    path: str
    status: int
    headers: dict[str, str]
    body: RuleBody
    delay_ms: int
    enabled: bool

    @staticmethod
    def from_domain(rule: Rule) -> "RuleResponse":
        return RuleResponse(
            id=rule.id,
            sandbox_id=rule.sandbox_id,
            host=rule.host,
            method=rule.method,
            path=rule.path,
            status=rule.status,
            headers=rule.headers,
            body=rule.body,
            delay_ms=rule.delay_ms,
            enabled=rule.enabled,
        )


class ExternalHostResponse(BaseModel):
    id: str
    label: str
