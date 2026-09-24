import pytest

from application.reconciler import Reconciler
from application.rule_service import RuleConflictError, RuleNotFoundError, RuleService
from domain.rule import ExternalHost
from tests.conftest import FakeStubStore, InMemoryRuleRepository


def make_service() -> RuleService:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    return RuleService(repository, reconciler)


def test_create_rule_persists_and_reconciles() -> None:
    service = make_service()

    rule = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="post",
        path="/charge",
        status=402,
        headers={},
        body={"error": "card_declined"},
        delay_ms=0,
        enabled=True,
    )

    assert rule in service.list_rules()
    assert rule.method == "POST"


def test_toggle_rule_flips_enabled() -> None:
    service = make_service()
    rule = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    toggled = service.toggle_rule(rule.id)

    assert toggled.enabled is False
    assert service.get_rule(rule.id).enabled is False


def test_delete_rule_removes_it() -> None:
    service = make_service()
    rule = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.WEATHER,
        method="GET",
        path="/weather",
        status=200,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    service.delete_rule(rule.id)

    with pytest.raises(RuleNotFoundError):
        service.get_rule(rule.id)


def test_get_missing_rule_raises() -> None:
    service = make_service()

    with pytest.raises(RuleNotFoundError):
        service.get_rule("missing")


def test_list_rules_filters_by_sandbox_id() -> None:
    service = make_service()
    service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )
    service.create_rule(
        sandbox_id="team-c",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    filtered = service.list_rules(sandbox_id="test-123")

    assert len(filtered) == 1
    assert filtered[0].sandbox_id == "test-123"


def test_list_rules_without_sandbox_id_returns_everything() -> None:
    service = make_service()
    service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.WEATHER,
        method="GET",
        path="/weather",
        status=200,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    assert len(service.list_rules()) == 1


def test_create_rule_conflicts_on_same_tuple() -> None:
    service = make_service()
    service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    with pytest.raises(RuleConflictError):
        service.create_rule(
            sandbox_id="test-123",
            host=ExternalHost.PAYMENTS,
            method="POST",
            path="/charge",
            status=500,
            headers={},
            body=None,
            delay_ms=0,
            enabled=True,
        )


def test_create_rule_allows_different_path() -> None:
    service = make_service()
    service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    rule = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/refund",
        status=200,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    assert rule.path == "/refund"


def test_update_rule_conflicts_with_another_rule_same_tuple() -> None:
    service = make_service()
    service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )
    second = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/refund",
        status=200,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    with pytest.raises(RuleConflictError):
        service.update_rule(second.id, path="/charge")


def test_update_rule_does_not_conflict_with_itself() -> None:
    service = make_service()
    rule = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    updated = service.update_rule(rule.id, status=500)

    assert updated.status == 500


def test_create_rule_upserts_only_that_rule_stub() -> None:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    service = RuleService(repository, reconciler)

    service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    assert stubs.upsert_calls == 1
    assert stubs.list_calls == 0


def test_delete_rule_removes_only_that_stub() -> None:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    service = RuleService(repository, reconciler)
    rule = service.create_rule(
        sandbox_id="test-123",
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body=None,
        delay_ms=0,
        enabled=True,
    )

    service.delete_rule(rule.id)

    assert stubs.delete_calls == 1
    assert rule.id not in stubs.stubs
