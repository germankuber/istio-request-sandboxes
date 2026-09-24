from application.rule_to_stub import rule_to_stub
from domain.rule import ExternalHost, Rule, RuleBody


def make_rule(
    sandbox_id: str = "test-123",
    host: ExternalHost = ExternalHost.PAYMENTS,
    method: str = "post",
    path: str = "/charge",
    status: int = 402,
    headers: dict[str, str] | None = None,
    body: RuleBody = None,
    delay_ms: int = 0,
    enabled: bool = True,
) -> Rule:
    return Rule.new(
        sandbox_id=sandbox_id,
        host=host,
        method=method,
        path=path,
        status=status,
        headers=headers if headers is not None else {"X-Custom": "1"},
        body=body if body is not None else {"error": "card_declined"},
        delay_ms=delay_ms,
        enabled=enabled,
    )


def test_rule_to_stub_maps_matcher_fields() -> None:
    rule = make_rule()

    stub = rule_to_stub(rule)

    assert stub.id == rule.id
    assert stub.rule_id == rule.id
    assert stub.priority == 1
    assert stub.host_contains == "external-payments"
    assert stub.method == "POST"
    assert stub.url_path == "/charge"
    assert stub.header_name == "X-Sandbox-ID"
    assert stub.header_equal_to == "test-123"


def test_rule_to_stub_carries_response_and_adds_mock_header() -> None:
    rule = make_rule()

    stub = rule_to_stub(rule)

    assert stub.status == 402
    assert stub.body == {"error": "card_declined"}
    assert stub.delay_ms == 0
    assert stub.headers["X-Mock"] == "true"
    assert stub.headers["X-Custom"] == "1"


def test_rule_to_stub_for_weather_host() -> None:
    rule = make_rule(host=ExternalHost.WEATHER, method="get", path="/weather", status=200)

    stub = rule_to_stub(rule)

    assert stub.host_contains == "external-weather"
    assert stub.method == "GET"
