import logging
from dataclasses import dataclass

from application.rule_to_stub import rule_to_stub
from domain.ports import RuleRepository, StubStore
from domain.rule import Rule

logger = logging.getLogger("mock-manager")


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    upserted: tuple[str, ...]
    removed: tuple[str, ...]
    failed: tuple[str, ...]


class Reconciler:
    def __init__(self, rules: RuleRepository, stubs: StubStore) -> None:
        self._rules = rules
        self._stubs = stubs

    def reconcile(self) -> ReconcileResult:
        enabled_rules = [rule for rule in self._rules.list_all() if rule.enabled]
        desired_stub_ids = {rule.id for rule in enabled_rules}

        upserted: list[str] = []
        failed: list[str] = []
        for rule in enabled_rules:
            try:
                self._stubs.upsert(rule_to_stub(rule))
            except Exception:
                logger.exception("failed to upsert stub for rule_id=%s", rule.id)
                failed.append(rule.id)
            else:
                upserted.append(rule.id)

        removed: list[str] = []
        for stub_id in self._stubs.list_managed_stub_ids() - desired_stub_ids:
            try:
                self._stubs.delete(stub_id)
            except Exception:
                logger.exception("failed to delete stub_id=%s", stub_id)
                failed.append(stub_id)
            else:
                removed.append(stub_id)

        return ReconcileResult(
            upserted=tuple(upserted), removed=tuple(removed), failed=tuple(failed)
        )

    def reconcile_one(self, rule: Rule) -> None:
        if rule.enabled:
            self._stubs.upsert(rule_to_stub(rule))
        else:
            self._stubs.delete(rule.id)

    def remove_one(self, rule_id: str) -> None:
        self._stubs.delete(rule_id)
