from application.reconciler import Reconciler
from domain.rule import ExternalHost, Rule
from domain.stub import WireMockStub
from tests.conftest import FakeStubStore, InMemoryRuleRepository


def make_rule(rule_id: str, enabled: bool = True, sandbox_id: str = "test-123") -> Rule:
    return Rule(
        id=rule_id,
        sandbox_id=sandbox_id,
        host=ExternalHost.PAYMENTS,
        method="POST",
        path="/charge",
        status=402,
        headers={},
        body={"error": "card_declined"},
        delay_ms=0,
        enabled=enabled,
    )


def test_reconcile_upserts_enabled_rules_only() -> None:
    repository = InMemoryRuleRepository(
        [make_rule("r1", enabled=True), make_rule("r2", enabled=False)]
    )
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)

    result = reconciler.reconcile()

    assert "r1" in stubs.stubs
    assert "r2" not in stubs.stubs
    assert result.upserted == ("r1",)
    assert result.removed == ()


def test_reconcile_removes_stub_when_rule_disabled() -> None:
    repository = InMemoryRuleRepository([make_rule("r1", enabled=True)])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    reconciler.reconcile()

    repository.save(make_rule("r1", enabled=False))
    result = reconciler.reconcile()

    assert "r1" not in stubs.stubs
    assert result.removed == ("r1",)


def test_reconcile_removes_stub_when_rule_deleted() -> None:
    repository = InMemoryRuleRepository([make_rule("r1", enabled=True)])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    reconciler.reconcile()

    repository.delete("r1")
    result = reconciler.reconcile()

    assert "r1" not in stubs.stubs
    assert result.removed == ("r1",)


def test_reconcile_is_idempotent() -> None:
    repository = InMemoryRuleRepository([make_rule("r1", enabled=True)])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)

    reconciler.reconcile()
    result = reconciler.reconcile()

    assert list(stubs.stubs.keys()) == ["r1"]
    assert result.upserted == ("r1",)
    assert result.removed == ()


class UnmanagedAwareStubStore(FakeStubStore):
    def list_managed_stub_ids(self) -> set[str]:
        return set()


def test_reconcile_never_touches_unmanaged_stub_ids() -> None:
    repository = InMemoryRuleRepository([])
    store = UnmanagedAwareStubStore()
    store.stubs["catch-all-manual"] = WireMockStub(
        id="catch-all-manual",
        rule_id="catch-all-manual",
        priority=1,
        host_contains="external-payments",
        method="POST",
        url_path="/charge",
        header_name="X-Sandbox-ID",
        header_equal_to="test-123",
        status=402,
        headers={},
        body={"error": "card_declined"},
        delay_ms=0,
    )
    reconciler = Reconciler(repository, store)

    result = reconciler.reconcile()

    assert "catch-all-manual" in store.stubs
    assert result.removed == ()


class UpsertFailingStubStore(FakeStubStore):
    def __init__(self, failing_ids: set[str]) -> None:
        super().__init__()
        self._failing_ids = failing_ids

    def upsert(self, stub) -> None:
        if stub.id in self._failing_ids:
            raise RuntimeError("wiremock unreachable")
        super().upsert(stub)


def test_reconcile_isolates_a_single_failing_rule() -> None:
    repository = InMemoryRuleRepository(
        [make_rule("bad"), make_rule("good")]
    )
    store = UpsertFailingStubStore(failing_ids={"bad"})
    reconciler = Reconciler(repository, store)

    result = reconciler.reconcile()

    assert "good" in store.stubs
    assert "bad" not in store.stubs
    assert result.upserted == ("good",)
    assert result.failed == ("bad",)


def test_reconcile_one_upserts_single_rule_stub() -> None:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    rule = make_rule("r1", enabled=True)

    reconciler.reconcile_one(rule)

    assert "r1" in stubs.stubs
    assert stubs.upsert_calls == 1
    assert stubs.list_calls == 0


def test_reconcile_one_removes_stub_when_rule_disabled() -> None:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    reconciler.reconcile_one(make_rule("r1", enabled=True))

    reconciler.reconcile_one(make_rule("r1", enabled=False))

    assert "r1" not in stubs.stubs


def test_remove_one_deletes_stub_by_id() -> None:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    reconciler.reconcile_one(make_rule("r1", enabled=True))

    reconciler.remove_one("r1")

    assert "r1" not in stubs.stubs
    assert stubs.delete_calls == 1
