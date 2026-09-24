from domain.rule import Rule
from domain.stub import WireMockStub

SANDBOX_HEADER = "X-Sandbox-ID"
MOCK_HEADER = "X-Mock"


def rule_to_stub(rule: Rule) -> WireMockStub:
    return WireMockStub(
        id=rule.id,
        rule_id=rule.id,
        priority=1,
        host_contains=rule.host.value,
        method=rule.method,
        url_path=rule.path,
        header_name=SANDBOX_HEADER,
        header_equal_to=rule.sandbox_id,
        status=rule.status,
        headers={**rule.headers, MOCK_HEADER: "true"},
        body=rule.body,
        delay_ms=rule.delay_ms,
    )
