from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import router
from application.reconciler import Reconciler
from application.rule_service import RuleService
from tests.conftest import FakeStubStore, InMemoryRuleRepository


def make_client() -> TestClient:
    repository = InMemoryRuleRepository([])
    stubs = FakeStubStore()
    reconciler = Reconciler(repository, stubs)
    service = RuleService(repository, reconciler)
    app = FastAPI()
    app.include_router(router)
    app.state.rule_service = service
    return TestClient(app)


def rule_payload(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "sandbox_id": "test-123",
        "host": "external-payments",
        "method": "POST",
        "path": "/charge",
        "status": 402,
        "headers": {},
        "body": {"error": "card_declined"},
        "delay_ms": 0,
        "enabled": True,
    }
    payload.update(overrides)
    return payload


def test_create_rule_returns_201() -> None:
    client = make_client()

    response = client.post("/rules", json=rule_payload())

    assert response.status_code == 201


def test_create_duplicate_rule_returns_409() -> None:
    client = make_client()
    client.post("/rules", json=rule_payload())

    response = client.post("/rules", json=rule_payload())

    assert response.status_code == 409


def test_create_rule_with_different_path_is_allowed() -> None:
    client = make_client()
    client.post("/rules", json=rule_payload())

    response = client.post("/rules", json=rule_payload(path="/refund"))

    assert response.status_code == 201


def test_update_rule_to_duplicate_tuple_returns_409() -> None:
    client = make_client()
    client.post("/rules", json=rule_payload())
    second = client.post("/rules", json=rule_payload(path="/refund")).json()

    response = client.put(f"/rules/{second['id']}", json={"path": "/charge"})

    assert response.status_code == 409


def test_update_rule_keeping_its_own_tuple_is_allowed() -> None:
    client = make_client()
    created = client.post("/rules", json=rule_payload()).json()

    response = client.put(f"/rules/{created['id']}", json={"status": 500})

    assert response.status_code == 200
