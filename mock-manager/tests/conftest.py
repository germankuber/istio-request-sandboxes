from domain.stub import WireMockStub
from domain.rule import ExternalHost, Rule


class InMemoryRuleRepository:
    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules = {rule.id: rule for rule in (rules or [])}

    def list_all(self) -> list[Rule]:
        return list(self._rules.values())

    def get(self, rule_id: str) -> Rule | None:
        return self._rules.get(rule_id)

    def find_by_key(
        self, sandbox_id: str, host: ExternalHost, method: str, path: str
    ) -> Rule | None:
        for rule in self._rules.values():
            if (
                rule.sandbox_id == sandbox_id
                and rule.host == host
                and rule.method == method
                and rule.path == path
            ):
                return rule
        return None

    def save(self, rule: Rule) -> None:
        self._rules[rule.id] = rule

    def delete(self, rule_id: str) -> None:
        self._rules.pop(rule_id, None)


class FakeStubStore:
    def __init__(self) -> None:
        self.stubs: dict[str, WireMockStub] = {}
        self.upsert_calls = 0
        self.delete_calls = 0
        self.list_calls = 0

    def list_managed_stub_ids(self) -> set[str]:
        self.list_calls += 1
        return set(self.stubs.keys())

    def upsert(self, stub: WireMockStub) -> None:
        self.upsert_calls += 1
        self.stubs[stub.id] = stub

    def delete(self, stub_id: str) -> None:
        self.delete_calls += 1
        self.stubs.pop(stub_id, None)
