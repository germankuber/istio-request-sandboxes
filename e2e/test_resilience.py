import time

import pytest

SELF_HEAL_TIMEOUT_SECONDS = 60.0


@pytest.mark.disruptive
def test_wiremock_self_heals_after_mock_proxy_pod_restart(
    sandbox_factory, wait_for_phase, chain_json, kubectl_run, eventually
):
    def weather_mocked() -> bool:
        response = chain_json("e2e-heal")
        return response["downstream"]["downstream"]["d"]["external"]["weather"]["mocked"] is True

    payload = {
        "name": "e2e-heal",
        "services": [],
        "mocks": [
            {
                "host": "external-weather",
                "method": "GET",
                "path": "/weather",
                "status": 200,
                "body": {"city": "Testville", "temp_c": 1, "condition": "heal-check"},
                "enabled": True,
            }
        ],
    }
    created = sandbox_factory(payload)
    assert created.status_code == 201, created.text
    assert wait_for_phase("e2e-heal", "Ready", 60)

    assert eventually(weather_mocked, SELF_HEAL_TIMEOUT_SECONDS)

    pod_name = kubectl_run(
        "get", "pod", "-l", "app=mock-proxy", "-o", "jsonpath={.items[0].metadata.name}"
    ).stdout.strip()
    assert pod_name, "no mock-proxy pod found"

    try:
        kubectl_run("delete", "pod", pod_name)
        time.sleep(3.0)
    finally:
        new_pod_name = kubectl_run(
            "get", "pod", "-l", "app=mock-proxy", "-o", "jsonpath={.items[0].metadata.name}"
        ).stdout.strip()
        if new_pod_name:
            kubectl_run(
                "wait",
                "--for=condition=Ready",
                f"pod/{new_pod_name}",
                "--timeout=90s",
                check=False,
            )

    assert eventually(weather_mocked, SELF_HEAL_TIMEOUT_SECONDS)


@pytest.mark.disruptive
def test_sandbox_a1_still_ready_and_routes_correctly(client, chain_json):
    response = client.get("/sandboxes-api/sandboxes/sandbox-a-1")
    assert response.status_code == 200
    assert response.json()["status"]["phase"] == "Ready"

    routed = chain_json("sandbox-a-1")
    assert routed["version"] == "sandbox-a-1"
