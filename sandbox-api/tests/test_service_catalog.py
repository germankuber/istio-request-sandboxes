from application.service_catalog import is_sandboxable_app, sandboxable_services
from domain.sandbox import BaselineDeployment


def test_is_sandboxable_app_excludes_known_infra() -> None:
    assert is_sandboxable_app("frontend") is False
    assert is_sandboxable_app("postgres") is False
    assert is_sandboxable_app("mock-manager") is False
    assert is_sandboxable_app("mock-proxy") is False
    assert is_sandboxable_app("sandbox-controller") is False
    assert is_sandboxable_app("sandbox-api") is False
    assert is_sandboxable_app("") is False


def test_is_sandboxable_app_allows_chain_services() -> None:
    for name in ("service-a", "service-b", "service-c", "service-d", "service-e"):
        assert is_sandboxable_app(name) is True


def test_sandboxable_services_filters_by_baseline_version_and_infra() -> None:
    deployments = [
        BaselineDeployment(app="frontend", version="baseline", env={}),
        BaselineDeployment(app="postgres", version="baseline", env={}),
        BaselineDeployment(app="postgres", version="sandbox", env={}),
        BaselineDeployment(app="mock-manager", version="baseline", env={}),
        BaselineDeployment(app="sandbox-controller", version=None, env={}),
        BaselineDeployment(app="service-c", version="baseline", env={"DATABASE_URL": "postgresql://x"}),
        BaselineDeployment(app="service-c", version="test-123", env={"DATABASE_URL": "postgresql://x"}),
        BaselineDeployment(app="service-d", version="baseline", env={}),
    ]

    result = sandboxable_services(deployments)

    assert [service.name for service in result] == ["service-c", "service-d"]


def test_sandboxable_services_marks_uses_db_from_database_url_env() -> None:
    deployments = [
        BaselineDeployment(app="service-c", version="baseline", env={"DATABASE_URL": "postgresql://x"}),
        BaselineDeployment(app="service-d", version="baseline", env={"EXTERNAL_PAYMENTS_URL": "http://x"}),
    ]

    result = sandboxable_services(deployments)

    by_name = {service.name: service.uses_db for service in result}
    assert by_name["service-c"] is True
    assert by_name["service-d"] is False


def test_sandboxable_services_sorts_by_name() -> None:
    deployments = [
        BaselineDeployment(app="service-e", version="baseline", env={}),
        BaselineDeployment(app="service-a", version="baseline", env={}),
    ]

    result = sandboxable_services(deployments)

    assert [service.name for service in result] == ["service-a", "service-e"]
