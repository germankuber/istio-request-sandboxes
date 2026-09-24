from application.spec_parsing import parse_sandbox
from domain.models import EnvOverride, MockRuleSpec, ServiceOverride


def test_parse_sandbox_builds_services_and_mocks() -> None:
    spec = {
        "services": [
            {
                "name": "service-c",
                "env": [{"name": "DATABASE_URL", "value": "postgresql://poc:poc@postgres-sandbox:5432/catalog"}],
            },
            {"name": "service-d", "image": "service-d:pr-7"},
        ],
        "mocks": [
            {"host": "external-payments", "method": "POST", "path": "/charge", "status": 402, "body": {"error": "card_declined"}},
        ],
    }

    sandbox = parse_sandbox("test-123", spec)

    assert sandbox.sandbox_id == "test-123"
    assert sandbox.services == (
        ServiceOverride(
            name="service-c",
            env=(EnvOverride(name="DATABASE_URL", value="postgresql://poc:poc@postgres-sandbox:5432/catalog"),),
        ),
        ServiceOverride(name="service-d", image="service-d:pr-7"),
    )
    assert sandbox.mocks == (
        MockRuleSpec(host="external-payments", method="POST", path="/charge", status=402, body={"error": "card_declined"}),
    )


def test_parse_sandbox_defaults_mock_enabled_to_true() -> None:
    spec = {"services": [], "mocks": [{"host": "external-weather", "method": "GET", "path": "/weather", "status": 200, "body": {}}]}

    sandbox = parse_sandbox("team-b", spec)

    assert sandbox.mocks[0].enabled is True


def test_parse_sandbox_handles_missing_services_and_mocks_keys() -> None:
    sandbox = parse_sandbox("team-x", {})

    assert sandbox.services == ()
    assert sandbox.mocks == ()
