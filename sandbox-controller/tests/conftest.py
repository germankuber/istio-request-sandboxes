from domain.mocks import ExistingMockRule
from domain.models import MockRuleSpec, Sandbox


class FakeDeploymentGateway:
    def __init__(self, baselines: dict[str, dict] | None = None) -> None:
        self.baselines = baselines or {}
        self.applied: dict[tuple[str, str], dict] = {}
        self.deleted: set[tuple[str, str]] = set()
        self.ready: set[tuple[str, str]] = set()

    def get_baseline(self, service_name: str) -> dict:
        return self.baselines[service_name]

    def apply_sandbox_deployment(self, manifest: dict, owner: Sandbox) -> None:
        self.applied[(manifest["metadata"]["labels"]["app"], owner.sandbox_id)] = manifest

    def delete_sandbox_deployment(self, service_name: str, sandbox_id: str) -> None:
        self.deleted.add((service_name, sandbox_id))
        self.applied.pop((service_name, sandbox_id), None)

    def list_managed_service_names(self, sandbox_id: str) -> tuple[str, ...]:
        return tuple(service for service, sid in self.applied if sid == sandbox_id)

    def is_ready(self, service_name: str, sandbox_id: str) -> bool:
        return (service_name, sandbox_id) in self.ready


class FakeRoutingGateway:
    def __init__(self, targets: dict[str, tuple] | None = None) -> None:
        self.targets = targets or {}
        self.destination_rules: dict[str, dict] = {}
        self.virtual_services: dict[str, dict] = {}

    def route_targets(self, service_name: str) -> tuple:
        return self.targets.get(service_name, ())

    def apply_destination_rule(self, manifest: dict) -> None:
        self.destination_rules[manifest["metadata"]["name"]] = manifest

    def apply_virtual_service(self, manifest: dict) -> None:
        self.virtual_services[manifest["metadata"]["name"]] = manifest

    def delete_destination_rule(self, service_name: str) -> None:
        self.destination_rules.pop(service_name, None)

    def delete_virtual_service(self, service_name: str) -> None:
        self.virtual_services.pop(service_name, None)


class FakeMockGateway:
    def __init__(self, rules: list[ExistingMockRule] | None = None) -> None:
        self.rules: dict[str, ExistingMockRule] = {rule.id: rule for rule in (rules or [])}
        self.created: list[tuple[str, MockRuleSpec]] = []
        self._next_id = 0

    def list_rules(self, sandbox_id: str) -> tuple[ExistingMockRule, ...]:
        return tuple(rule for rule in self.rules.values() if rule.sandbox_id == sandbox_id)

    def list_all_rules(self) -> tuple[ExistingMockRule, ...]:
        return tuple(self.rules.values())

    def create_rule(self, sandbox_id: str, mock: MockRuleSpec) -> None:
        self._next_id += 1
        rule_id = f"rule-{self._next_id}"
        self.created.append((sandbox_id, mock))
        self.rules[rule_id] = ExistingMockRule(
            id=rule_id, sandbox_id=sandbox_id, host=mock.host, method=mock.method.upper(), path=mock.path
        )

    def delete_rule(self, rule_id: str) -> None:
        self.rules.pop(rule_id, None)
