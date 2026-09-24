import time


def _find_payments_rule_id(client, sandbox_id: str) -> str:
    response = client.get("/mocks/rules", params={"sandbox_id": sandbox_id})
    response.raise_for_status()
    for rule in response.json():
        if rule["host"] == "external-payments":
            return rule["id"]
    raise AssertionError(f"no external-payments rule found for sandbox_id={sandbox_id}")


def _payments_mock_payload() -> dict:
    return {
        "host": "external-payments",
        "method": "POST",
        "path": "/charge",
        "status": 402,
        "body": {"error": "card_declined"},
        "enabled": True,
    }


def test_mock_rule_toggle_and_isolation(
    client, sandbox_factory, wait_for_phase, chain_json
):
    mocked = sandbox_factory(
        {
            "name": "e2e-mocktoggle",
            "services": [{"name": "service-c", "use_migrated_db": True}, {"name": "service-d"}],
            "mocks": [_payments_mock_payload()],
        }
    )
    isolated = sandbox_factory(
        {
            "name": "e2e-mockiso",
            "services": [{"name": "service-c", "use_migrated_db": True}],
            "mocks": [],
        }
    )
    assert mocked.status_code == 201, mocked.text
    assert isolated.status_code == 201, isolated.text
    assert wait_for_phase("e2e-mocktoggle", "Ready", 120)
    assert wait_for_phase("e2e-mockiso", "Ready", 120)

    rule_id = _find_payments_rule_id(client, "e2e-mocktoggle")

    toggle_off = client.post(f"/mocks/rules/{rule_id}/toggle")
    assert toggle_off.status_code == 200
    response = chain_json("e2e-mocktoggle")
    assert response["downstream"]["downstream"]["d"]["external"]["payments"]["mocked"] is False

    toggle_on = client.post(f"/mocks/rules/{rule_id}/toggle")
    assert toggle_on.status_code == 200
    response = chain_json("e2e-mocktoggle")
    assert response["downstream"]["downstream"]["d"]["external"]["payments"]["mocked"] is True

    isolated_response = chain_json("e2e-mockiso")
    isolated_downstream = isolated_response["downstream"]["downstream"]
    assert isolated_downstream["d"]["external"]["payments"]["mocked"] is False


def test_controller_does_not_override_manual_mock_toggle(
    client, sandbox_factory, wait_for_phase, kubectl_run
):
    created = sandbox_factory(
        {
            "name": "e2e-reconcile",
            "services": [{"name": "service-c", "use_migrated_db": True}, {"name": "service-d"}],
            "mocks": [_payments_mock_payload()],
        }
    )
    assert created.status_code == 201, created.text
    assert wait_for_phase("e2e-reconcile", "Ready", 120)

    rule_id = _find_payments_rule_id(client, "e2e-reconcile")
    client.post(f"/mocks/rules/{rule_id}/toggle")

    def _rule_enabled() -> bool:
        response = client.get("/mocks/rules", params={"sandbox_id": "e2e-reconcile"})
        response.raise_for_status()
        rule = next(rule for rule in response.json() if rule["id"] == rule_id)
        return bool(rule["enabled"])

    assert _rule_enabled() is False

    kubectl_run(
        "annotate", "sandbox", "e2e-reconcile", f"touch={int(time.time())}", "--overwrite"
    )
    time.sleep(12.0)

    assert _rule_enabled() is False
