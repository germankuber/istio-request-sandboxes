import uuid
from dataclasses import dataclass, replace
from enum import StrEnum


class ExternalHost(StrEnum):
    PAYMENTS = "external-payments"
    WEATHER = "external-weather"


RuleBody = dict[str, object] | list[object] | str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class Rule:
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
    def new(
        sandbox_id: str,
        host: ExternalHost,
        method: str,
        path: str,
        status: int,
        headers: dict[str, str],
        body: RuleBody,
        delay_ms: int,
        enabled: bool,
    ) -> "Rule":
        return Rule(
            id=str(uuid.uuid4()),
            sandbox_id=sandbox_id,
            host=host,
            method=method.upper(),
            path=path,
            status=status,
            headers=dict(headers),
            body=body,
            delay_ms=delay_ms,
            enabled=enabled,
        )

    def with_updates(self, **changes: object) -> "Rule":
        if "method" in changes and changes["method"] is not None:
            changes = {**changes, "method": str(changes["method"]).upper()}
        return replace(self, **changes)
