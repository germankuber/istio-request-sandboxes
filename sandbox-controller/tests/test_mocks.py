from domain.mocks import (
    ExistingMockRule,
    plan_mock_rule_creates,
    plan_mock_rule_deletes,
    plan_orphan_rule_deletes,
)
from domain.models import MockRuleSpec


def test_plan_creates_returns_all_when_nothing_exists() -> None:
    desired = (MockRuleSpec(host="external-payments", method="POST", path="/charge", status=402, body=None),)

    plan = plan_mock_rule_creates("test-123", desired, ())

    assert plan == desired


def test_plan_creates_skips_rule_already_matching_sandbox_host_method_path() -> None:
    desired = (MockRuleSpec(host="external-payments", method="POST", path="/charge", status=402, body=None),)
    existing = (
        ExistingMockRule(
            id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"
        ),
    )

    plan = plan_mock_rule_creates("test-123", desired, existing)

    assert plan == ()


def test_plan_creates_is_case_insensitive_on_method() -> None:
    desired = (MockRuleSpec(host="external-payments", method="post", path="/charge", status=402, body=None),)
    existing = (
        ExistingMockRule(
            id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"
        ),
    )

    plan = plan_mock_rule_creates("test-123", desired, existing)

    assert plan == ()


def test_plan_creates_ignores_rules_belonging_to_other_sandboxes() -> None:
    desired = (MockRuleSpec(host="external-payments", method="POST", path="/charge", status=402, body=None),)
    existing = (
        ExistingMockRule(
            id="rule-1", sandbox_id="team-c", host="external-payments", method="POST", path="/charge"
        ),
    )

    plan = plan_mock_rule_creates("test-123", desired, existing)

    assert plan == desired


def test_plan_deletes_returns_only_ids_for_given_sandbox() -> None:
    existing = (
        ExistingMockRule(id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"),
        ExistingMockRule(id="rule-2", sandbox_id="team-c", host="external-payments", method="POST", path="/charge"),
        ExistingMockRule(id="rule-3", sandbox_id="test-123", host="external-weather", method="GET", path="/weather"),
    )

    plan = plan_mock_rule_deletes("test-123", existing)

    assert set(plan) == {"rule-1", "rule-3"}


def test_plan_orphan_deletes_keeps_rules_for_known_sandboxes() -> None:
    existing = (
        ExistingMockRule(id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"),
    )

    plan = plan_orphan_rule_deletes(existing, frozenset({"test-123"}))

    assert plan == ()


def test_plan_orphan_deletes_collects_rules_for_unknown_sandbox_ids() -> None:
    existing = (
        ExistingMockRule(id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"),
        ExistingMockRule(id="rule-2", sandbox_id="deleted-sandbox", host="external-weather", method="GET", path="/weather"),
    )

    plan = plan_orphan_rule_deletes(existing, frozenset({"test-123"}))

    assert plan == ("rule-2",)


def test_plan_orphan_deletes_returns_empty_for_empty_inputs() -> None:
    assert plan_orphan_rule_deletes((), frozenset()) == ()


def test_plan_orphan_deletes_refuses_to_sweep_when_no_sandbox_is_known() -> None:
    existing = (
        ExistingMockRule(id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"),
        ExistingMockRule(id="rule-2", sandbox_id="team-c", host="external-weather", method="GET", path="/weather"),
    )

    plan = plan_orphan_rule_deletes(existing, frozenset())

    assert plan == ()


def test_plan_orphan_deletes_returns_nothing_when_every_sandbox_is_known() -> None:
    existing = (
        ExistingMockRule(id="rule-1", sandbox_id="test-123", host="external-payments", method="POST", path="/charge"),
        ExistingMockRule(id="rule-2", sandbox_id="team-c", host="external-weather", method="GET", path="/weather"),
    )

    plan = plan_orphan_rule_deletes(existing, frozenset({"test-123", "team-c"}))

    assert plan == ()


def test_plan_orphan_deletes_also_collects_rule_for_manually_created_sandbox_id_never_a_cr() -> None:
    existing = (
        ExistingMockRule(id="rule-1", sandbox_id="never-was-a-cr", host="external-payments", method="POST", path="/charge"),
    )

    plan = plan_orphan_rule_deletes(existing, frozenset({"test-123"}))

    assert plan == ("rule-1",)
