def test_invalid_sandbox_name_returns_422(client):
    response = client.post(
        "/sandboxes-api/sandboxes",
        json={"name": "E2E_Invalid_Name!", "services": [], "mocks": []},
    )
    assert response.status_code == 422


def test_duplicate_sandbox_name_returns_409(sandbox_factory, wait_for_phase):
    payload = {"name": "e2e-dup", "services": [{"name": "service-c"}], "mocks": []}
    first = sandbox_factory(payload)
    assert first.status_code == 201, first.text
    assert wait_for_phase("e2e-dup", "Ready", 90)

    second = sandbox_factory(payload)
    assert second.status_code == 409


def test_foreign_image_override_returns_422(client):
    response = client.post(
        "/sandboxes-api/sandboxes",
        json={
            "name": "e2e-badimg",
            "services": [{"name": "service-c", "image": "evil/registry:latest"}],
            "mocks": [],
        },
    )
    assert response.status_code == 422


def test_invalid_env_var_name_returns_422(client):
    response = client.post(
        "/sandboxes-api/sandboxes",
        json={
            "name": "e2e-badenv",
            "services": [{"name": "service-c", "env": [{"name": "1BAD", "value": "x"}]}],
            "mocks": [],
        },
    )
    assert response.status_code == 422


def test_duplicate_mock_rule_returns_409(client):
    rule_payload = {
        "sandbox_id": "e2e-dupmock",
        "host": "external-weather",
        "method": "GET",
        "path": "/weather",
        "status": 200,
        "body": {"ok": True},
        "enabled": True,
    }
    try:
        first = client.post("/mocks/rules", json=rule_payload)
        assert first.status_code == 201, first.text

        second = client.post("/mocks/rules", json=rule_payload)
        assert second.status_code == 409
    finally:
        rules = client.get("/mocks/rules", params={"sandbox_id": "e2e-dupmock"}).json()
        for rule in rules:
            client.delete(f"/mocks/rules/{rule['id']}")
