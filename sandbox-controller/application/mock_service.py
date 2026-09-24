import logging
from typing import Callable

from domain.models import Sandbox
from domain.mocks import plan_mock_rule_creates, plan_mock_rule_deletes, plan_orphan_rule_deletes
from domain.ports import MockGateway


class MockService:
    def __init__(self, gateway: MockGateway) -> None:
        self._gateway = gateway

    def seed(self, sandbox: Sandbox) -> None:
        if not sandbox.mocks:
            return
        existing = self._gateway.list_rules(sandbox.sandbox_id)
        for mock in plan_mock_rule_creates(sandbox.sandbox_id, sandbox.mocks, existing):
            self._gateway.create_rule(sandbox.sandbox_id, mock)

    def delete_all(self, sandbox_id: str) -> None:
        existing = self._gateway.list_rules(sandbox_id)
        for rule_id in plan_mock_rule_deletes(sandbox_id, existing):
            self._gateway.delete_rule(rule_id)

    def collect_orphans(
        self, known_sandbox_ids: Callable[[], frozenset[str]], logger: logging.Logger
    ) -> tuple[str, ...]:
        all_rules = self._gateway.list_all_rules()
        deleted: list[str] = []
        for rule_id in plan_orphan_rule_deletes(all_rules, known_sandbox_ids()):
            try:
                self._gateway.delete_rule(rule_id)
            except Exception:
                logger.exception("failed to delete orphaned mock rule %s", rule_id)
                continue
            deleted.append(rule_id)
        return tuple(deleted)
