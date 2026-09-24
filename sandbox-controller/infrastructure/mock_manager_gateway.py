import httpx

from domain.mocks import ExistingMockRule
from domain.models import MockRuleSpec


class MockManagerGateway:
    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def list_rules(self, sandbox_id: str) -> tuple[ExistingMockRule, ...]:
        response = httpx.get(
            f"{self._base_url}/rules", params={"sandbox_id": sandbox_id}, timeout=self._timeout
        )
        response.raise_for_status()
        return tuple(_to_existing_rule(item) for item in response.json())

    def list_all_rules(self) -> tuple[ExistingMockRule, ...]:
        response = httpx.get(f"{self._base_url}/rules", timeout=self._timeout)
        response.raise_for_status()
        return tuple(_to_existing_rule(item) for item in response.json())

    def create_rule(self, sandbox_id: str, mock: MockRuleSpec) -> None:
        payload = {
            "sandbox_id": sandbox_id,
            "host": mock.host,
            "method": mock.method,
            "path": mock.path,
            "status": mock.status,
            "headers": {},
            "body": mock.body,
            "delay_ms": 0,
            "enabled": mock.enabled,
        }
        response = httpx.post(f"{self._base_url}/rules", json=payload, timeout=self._timeout)
        response.raise_for_status()

    def delete_rule(self, rule_id: str) -> None:
        response = httpx.delete(f"{self._base_url}/rules/{rule_id}", timeout=self._timeout)
        if response.status_code != 404:
            response.raise_for_status()


def _to_existing_rule(item: dict) -> ExistingMockRule:
    return ExistingMockRule(
        id=item["id"],
        sandbox_id=item["sandbox_id"],
        host=item["host"],
        method=item["method"],
        path=item["path"],
    )
