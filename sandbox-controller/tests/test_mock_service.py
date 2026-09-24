import logging

import pytest

from application.mock_service import MockService
from domain.mocks import ExistingMockRule
from domain.models import MockRuleSpec, Sandbox
from tests.conftest import FakeMockGateway


def make_sandbox(mocks: tuple[MockRuleSpec, ...]) -> Sandbox:
    return Sandbox(sandbox_id="test-123", services=(), mocks=mocks)


def test_seed_creates_declared_mocks_when_none_exist() -> None:
    gateway = FakeMockGateway()
    sandbox = make_sandbox((MockRuleSpec(host="external-payments", method="POST", path="/charge", status=402, body=None),))

    MockService(gateway).seed(sandbox)

    assert len(gateway.created) == 1
    assert gateway.created[0][0] == "test-123"


def test_seed_does_not_recreate_or_touch_existing_rule() -> None:
    existing = ExistingMockRule(
        id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"
    )
    gateway = FakeMockGateway([existing])
    sandbox = make_sandbox((MockRuleSpec(host="external-payments", method="POST", path="/charge", status=402, body=None),))

    MockService(gateway).seed(sandbox)

    assert gateway.created == []
    assert gateway.rules["rule-1"] == existing


def test_seed_with_no_declared_mocks_does_not_call_gateway() -> None:
    gateway = FakeMockGateway()
    sandbox = make_sandbox(())

    MockService(gateway).seed(sandbox)

    assert gateway.created == []


def test_delete_all_removes_every_rule_for_that_sandbox_only() -> None:
    gateway = FakeMockGateway(
        [
            ExistingMockRule(id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"),
            ExistingMockRule(id="rule-2", sandbox_id="team-c", host="external-payments", method="POST", path="/charge"),
        ]
    )

    MockService(gateway).delete_all("test-123")

    assert "rule-1" not in gateway.rules
    assert "rule-2" in gateway.rules


def test_collect_orphans_deletes_rules_for_unknown_sandbox_ids() -> None:
    gateway = FakeMockGateway(
        [
            ExistingMockRule(
                id="rule-orphan", sandbox_id="deleted-sandbox", host="external-payments", method="POST", path="/charge"
            ),
            ExistingMockRule(
                id="rule-keep", sandbox_id="sandbox-a-1", host="external-payments", method="POST", path="/charge"
            ),
        ]
    )
    logger = logging.getLogger("test-collect-orphans")

    deleted = MockService(gateway).collect_orphans(lambda: frozenset({"sandbox-a-1"}), logger)

    assert deleted == ("rule-orphan",)
    assert "rule-orphan" not in gateway.rules
    assert "rule-keep" in gateway.rules


def test_collect_orphans_with_no_orphans_deletes_nothing() -> None:
    gateway = FakeMockGateway(
        [ExistingMockRule(id="rule-keep", sandbox_id="sandbox-a-1", host="external-payments", method="POST", path="/charge")]
    )
    logger = logging.getLogger("test-collect-orphans")

    deleted = MockService(gateway).collect_orphans(lambda: frozenset({"sandbox-a-1"}), logger)

    assert deleted == ()
    assert "rule-keep" in gateway.rules


def test_collect_orphans_lists_mock_rules_before_listing_sandbox_ids() -> None:
    events: list[str] = []

    class RecordingMockGateway(FakeMockGateway):
        def list_all_rules(self) -> tuple[ExistingMockRule, ...]:
            events.append("list_all_rules")
            return super().list_all_rules()

    def known_sandbox_ids() -> frozenset[str]:
        events.append("known_sandbox_ids")
        return frozenset()

    gateway = RecordingMockGateway(
        [ExistingMockRule(id="rule-1", sandbox_id="sandbox-a-1", host="external-payments", method="POST", path="/charge")]
    )
    logger = logging.getLogger("test-collect-orphans-ordering")

    MockService(gateway).collect_orphans(known_sandbox_ids, logger)

    assert events == ["list_all_rules", "known_sandbox_ids"]


class PartiallyFailingMockGateway(FakeMockGateway):
    def __init__(self, rules: list[ExistingMockRule], failing_rule_id: str) -> None:
        super().__init__(rules)
        self._failing_rule_id = failing_rule_id

    def delete_rule(self, rule_id: str) -> None:
        if rule_id == self._failing_rule_id:
            raise RuntimeError("mock-manager unreachable")
        super().delete_rule(rule_id)


def test_collect_orphans_continues_after_one_rule_fails_to_delete(caplog: pytest.LogCaptureFixture) -> None:
    gateway = PartiallyFailingMockGateway(
        [
            ExistingMockRule(id="rule-fails", sandbox_id="deleted-a", host="external-payments", method="POST", path="/a"),
            ExistingMockRule(id="rule-succeeds", sandbox_id="deleted-b", host="external-payments", method="POST", path="/b"),
        ],
        failing_rule_id="rule-fails",
    )
    logger = logging.getLogger("test-collect-orphans-partial-failure")

    with caplog.at_level(logging.ERROR, logger="test-collect-orphans-partial-failure"):
        deleted = MockService(gateway).collect_orphans(lambda: frozenset({"sandbox-a-1"}), logger)

    assert deleted == ("rule-succeeds",)
    assert "rule-fails" in gateway.rules
    assert "rule-succeeds" not in gateway.rules
    assert "rule-fails" in caplog.text
