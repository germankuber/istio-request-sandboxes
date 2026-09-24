from dataclasses import dataclass

from domain.rule import RuleBody


@dataclass(frozen=True, slots=True)
class WireMockStub:
    id: str
    rule_id: str
    priority: int
    host_contains: str
    method: str
    url_path: str
    header_name: str
    header_equal_to: str
    status: int
    headers: dict[str, str]
    body: RuleBody
    delay_ms: int
