from dataclasses import dataclass

from domain.models import MockRuleSpec


@dataclass(frozen=True, slots=True)
class ExistingMockRule:
    id: str
    sandbox_id: str
    host: str
    method: str
    path: str


def plan_mock_rule_creates(
    sandbox_id: str,
    desired: tuple[MockRuleSpec, ...],
    existing: tuple[ExistingMockRule, ...],
) -> tuple[MockRuleSpec, ...]:
    existing_keys = {_existing_key(rule) for rule in existing if rule.sandbox_id == sandbox_id}
    return tuple(mock for mock in desired if _desired_key(sandbox_id, mock) not in existing_keys)


def plan_mock_rule_deletes(sandbox_id: str, existing: tuple[ExistingMockRule, ...]) -> tuple[str, ...]:
    return tuple(rule.id for rule in existing if rule.sandbox_id == sandbox_id)


def plan_orphan_rule_deletes(
    all_rules: tuple[ExistingMockRule, ...], known_sandbox_ids: frozenset[str]
) -> tuple[str, ...]:
    if not known_sandbox_ids:
        return ()
    return tuple(rule.id for rule in all_rules if rule.sandbox_id not in known_sandbox_ids)


def _existing_key(rule: ExistingMockRule) -> tuple[str, str, str, str]:
    return (rule.sandbox_id, rule.host, rule.method.upper(), rule.path)


def _desired_key(sandbox_id: str, mock: MockRuleSpec) -> tuple[str, str, str, str]:
    return (sandbox_id, mock.host, mock.method.upper(), mock.path)
