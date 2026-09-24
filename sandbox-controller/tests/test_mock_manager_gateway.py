import httpx
import pytest

from infrastructure.mock_manager_gateway import MockManagerGateway


class _FakeResponse:
    def __init__(self, payload: list[dict]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> list[dict]:
        return self._payload


def test_list_all_rules_requests_rules_endpoint_with_no_sandbox_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    captured_kwargs: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> _FakeResponse:
        captured["url"] = url
        captured_kwargs.update(kwargs)
        return _FakeResponse(
            [
                {
                    "id": "rule-1",
                    "sandbox_id": "test-123",
                    "host": "external-payments",
                    "method": "POST",
                    "path": "/charge",
                },
                {
                    "id": "rule-2",
                    "sandbox_id": "team-c",
                    "host": "external-weather",
                    "method": "GET",
                    "path": "/weather",
                },
            ]
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    gateway = MockManagerGateway("http://mock-manager")
    rules = gateway.list_all_rules()

    assert captured["url"] == "http://mock-manager/rules"
    assert "params" not in captured_kwargs
    assert {rule.id for rule in rules} == {"rule-1", "rule-2"}
    assert {rule.sandbox_id for rule in rules} == {"test-123", "team-c"}


def test_list_all_rules_returns_empty_tuple_when_no_rules_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _FakeResponse([]))

    gateway = MockManagerGateway("http://mock-manager")

    assert gateway.list_all_rules() == ()
