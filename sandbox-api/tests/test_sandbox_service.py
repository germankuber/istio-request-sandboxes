import pytest

from application.sandbox_service import SandboxService
from domain.errors import SandboxAlreadyExistsError, SandboxNotFoundError
from domain.sandbox import BaselineDeployment, MockRequest, ServiceRequest
from tests.conftest import FakeSandboxPort


def test_create_sandbox_persists_via_port() -> None:
    service = SandboxService(FakeSandboxPort())

    created = service.create_sandbox(
        "demo",
        services=(ServiceRequest(name="service-d", image=None, env=(), use_migrated_db=False),),
        mocks=(),
    )

    assert created["metadata"]["name"] == "demo"
    assert [item.name for item in service.list_sandboxes()] == ["demo"]


def test_create_sandbox_rejects_duplicate_name() -> None:
    port = FakeSandboxPort()
    service = SandboxService(port)
    service.create_sandbox("demo", services=(), mocks=())

    with pytest.raises(SandboxAlreadyExistsError):
        service.create_sandbox("demo", services=(), mocks=())


def test_create_sandbox_rejects_invalid_name() -> None:
    service = SandboxService(FakeSandboxPort())

    with pytest.raises(ValueError):
        service.create_sandbox("Bad_Name", services=(), mocks=())


def test_create_sandbox_expands_migrated_db_preset() -> None:
    service = SandboxService(FakeSandboxPort())

    created = service.create_sandbox(
        "demo",
        services=(ServiceRequest(name="service-c", image=None, env=(), use_migrated_db=True),),
        mocks=(MockRequest(host="external-payments", method="post", path="/charge", status=402, body=None, enabled=True),),
    )

    env_names = [item["name"] for item in created["spec"]["services"][0]["env"]]
    assert env_names == ["DATABASE_URL", "DB_PEER_SERVICE", "DB_SCHEMA"]


def test_get_sandbox_raises_when_missing() -> None:
    service = SandboxService(FakeSandboxPort())

    with pytest.raises(SandboxNotFoundError):
        service.get_sandbox("missing")


def test_delete_sandbox_removes_it() -> None:
    service = SandboxService(FakeSandboxPort())
    service.create_sandbox("demo", services=(), mocks=())

    service.delete_sandbox("demo")

    with pytest.raises(SandboxNotFoundError):
        service.get_sandbox("demo")


def test_delete_sandbox_raises_when_missing() -> None:
    service = SandboxService(FakeSandboxPort())

    with pytest.raises(SandboxNotFoundError):
        service.delete_sandbox("missing")


def test_list_services_delegates_to_service_catalog() -> None:
    deployments = [
        BaselineDeployment(app="service-c", version="baseline", env={"DATABASE_URL": "postgresql://x"}),
        BaselineDeployment(app="frontend", version="baseline", env={}),
    ]
    service = SandboxService(FakeSandboxPort(deployments=deployments))

    result = service.list_services()

    assert [item.name for item in result] == ["service-c"]
    assert result[0].uses_db is True


def test_list_sandboxes_defaults_phase_and_message_when_status_missing() -> None:
    freshly_created = {
        "metadata": {"name": "demo"},
        "spec": {"services": [], "mocks": []},
    }
    service = SandboxService(FakeSandboxPort(sandboxes={"demo": freshly_created}))

    [summary] = service.list_sandboxes()

    assert summary.phase == "Pending"
    assert summary.message == ""


def test_list_sandboxes_reports_deleting_while_finalizer_pending() -> None:
    terminating = {
        "metadata": {"name": "demo", "deletionTimestamp": "2026-09-24T15:00:00Z"},
        "spec": {"services": [], "mocks": []},
        "status": {"phase": "Ready", "message": "all sandboxed services available"},
    }
    service = SandboxService(FakeSandboxPort(sandboxes={"demo": terminating}))

    [summary] = service.list_sandboxes()

    assert summary.phase == "Deleting"
    assert summary.message == "cleaning up deployments, routes and mocks"
