from application.reconciler import Reconciler, ReconcileResult
from domain.ports import RuleRepository
from domain.rule import ExternalHost, Rule, RuleBody


class RuleNotFoundError(Exception):
    pass


class RuleConflictError(Exception):
    pass


class RuleService:
    def __init__(self, repository: RuleRepository, reconciler: Reconciler) -> None:
        self._repository = repository
        self._reconciler = reconciler

    def list_rules(self, sandbox_id: str | None = None) -> list[Rule]:
        rules = self._repository.list_all()
        if sandbox_id is None:
            return rules
        return [rule for rule in rules if rule.sandbox_id == sandbox_id]

    def get_rule(self, rule_id: str) -> Rule:
        rule = self._repository.get(rule_id)
        if rule is None:
            raise RuleNotFoundError(rule_id)
        return rule

    def create_rule(
        self,
        sandbox_id: str,
        host: ExternalHost,
        method: str,
        path: str,
        status: int,
        headers: dict[str, str],
        body: RuleBody,
        delay_ms: int,
        enabled: bool,
    ) -> Rule:
        rule = Rule.new(
            sandbox_id=sandbox_id,
            host=host,
            method=method,
            path=path,
            status=status,
            headers=headers,
            body=body,
            delay_ms=delay_ms,
            enabled=enabled,
        )
        self._raise_if_conflicting(rule)
        self._repository.save(rule)
        self._reconciler.reconcile_one(rule)
        return rule

    def update_rule(self, rule_id: str, **changes: object) -> Rule:
        existing = self.get_rule(rule_id)
        updated = existing.with_updates(**changes)
        self._raise_if_conflicting(updated)
        self._repository.save(updated)
        self._reconciler.reconcile_one(updated)
        return updated

    def delete_rule(self, rule_id: str) -> None:
        self.get_rule(rule_id)
        self._repository.delete(rule_id)
        self._reconciler.remove_one(rule_id)

    def toggle_rule(self, rule_id: str) -> Rule:
        existing = self.get_rule(rule_id)
        updated = existing.with_updates(enabled=not existing.enabled)
        self._repository.save(updated)
        self._reconciler.reconcile_one(updated)
        return updated

    def _raise_if_conflicting(self, rule: Rule) -> None:
        conflicting = self._repository.find_by_key(
            rule.sandbox_id, rule.host, rule.method, rule.path
        )
        if conflicting is not None and conflicting.id != rule.id:
            raise RuleConflictError(rule.id)

    def reconcile_now(self) -> ReconcileResult:
        return self._reconciler.reconcile()
