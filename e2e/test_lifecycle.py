import json
import threading
import time

import httpx
import pytest


def test_removing_a_service_returns_zero_non_200_responses(
    base_url, sandbox_factory, wait_for_phase, chain_json, kubectl_run
):
    payload = {
        "name": "e2e-removal",
        "services": [
            {"name": "service-c", "use_migrated_db": True},
            {"name": "service-d"},
        ],
        "mocks": [],
    }
    created = sandbox_factory(payload)
    assert created.status_code == 201, created.text
    assert wait_for_phase("e2e-removal", "Ready", 120)

    status_codes: list[int] = []
    stop_event = threading.Event()

    def poll() -> None:
        with httpx.Client(base_url=base_url, timeout=5.0) as poll_client:
            while not stop_event.is_set():
                try:
                    response = poll_client.get(
                        "/api/chain", headers={"X-Sandbox-ID": "e2e-removal"}
                    )
                    status_codes.append(response.status_code)
                except httpx.HTTPError:
                    status_codes.append(-1)
                time.sleep(0.3)

    poller = threading.Thread(target=poll, daemon=True)
    poller.start()
    time.sleep(1.0)

    current = kubectl_run("get", "sandbox", "e2e-removal", "-o", "json")
    spec = json.loads(current.stdout)
    remaining_services = [
        service for service in spec["spec"]["services"] if service["name"] != "service-d"
    ]
    patch_body = json.dumps({"spec": {"services": remaining_services}})
    kubectl_run("patch", "sandbox", "e2e-removal", "--type=merge", "-p", patch_body)

    time.sleep(9.0)
    stop_event.set()
    poller.join(timeout=5.0)

    non_200 = [code for code in status_codes if code != 200]
    assert non_200 == [], (
        f"non-200 responses while removing service-d: {non_200} "
        f"(total polled: {len(status_codes)})"
    )
    assert wait_for_phase("e2e-removal", "Ready", 60)

    response = chain_json("e2e-removal")
    assert response["downstream"]["downstream"]["d"]["version"] == "baseline"


@pytest.mark.disruptive
def test_orphaned_rules_are_garbage_collected_after_mock_manager_down_delete(
    client, sandbox_factory, wait_for_phase, wait_until_gone, wait_rollout_ready, kubectl_run
):
    payload = {
        "name": "e2e-mmdown",
        "services": [
            {"name": "service-c", "use_migrated_db": True},
            {"name": "service-d"},
        ],
        "mocks": [
            {
                "host": "external-payments",
                "method": "POST",
                "path": "/charge",
                "status": 402,
                "body": {"error": "card_declined"},
                "enabled": True,
            },
            {
                "host": "external-weather",
                "method": "GET",
                "path": "/weather",
                "status": 200,
                "body": {"city": "Testville"},
                "enabled": True,
            },
        ],
    }
    created = sandbox_factory(payload)
    assert created.status_code == 201, created.text
    assert wait_for_phase("e2e-mmdown", "Ready", 120)

    try:
        kubectl_run("scale", "deploy/mock-manager", "--replicas=0")
        time.sleep(3.0)

        delete_response = client.delete("/sandboxes-api/sandboxes/e2e-mmdown")
        assert delete_response.status_code == 204

        assert wait_until_gone("e2e-mmdown", 60.0)
    finally:
        kubectl_run("scale", "deploy/mock-manager", "--replicas=1")
        assert wait_rollout_ready("mock-manager", 90.0)

    deadline = time.monotonic() + 90.0
    remaining = None
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        try:
            response = client.get("/mocks/rules", params={"sandbox_id": "e2e-mmdown"})
            if response.status_code == 200:
                remaining = len(response.json())
                if remaining == 0:
                    break
        except httpx.HTTPError:
            pass
        time.sleep(2.5)

    assert remaining == 0, (
        f"orphaned rules for e2e-mmdown were not garbage collected within 90s "
        f"({remaining} left after {polls} polls)"
    )


def test_cleanup_leaves_no_leftover_deployments_routes_or_mock_rules(
    client, sandbox_factory, wait_for_phase, wait_until_gone, kubectl_run
):
    names = ["e2e-clean1", "e2e-clean2"]
    payloads = [
        {"name": names[0], "services": [{"name": "service-a"}], "mocks": []},
        {
            "name": names[1],
            "services": [{"name": "service-c", "use_migrated_db": True}],
            "mocks": [
                {
                    "host": "external-weather",
                    "method": "GET",
                    "path": "/weather",
                    "status": 200,
                    "body": {"ok": True},
                    "enabled": True,
                }
            ],
        },
    ]
    for payload in payloads:
        created = sandbox_factory(payload)
        assert created.status_code == 201, created.text
    for name in names:
        assert wait_for_phase(name, "Ready", 120)

    for name in names:
        client.delete(f"/sandboxes-api/sandboxes/{name}")
    for name in names:
        assert wait_until_gone(name, 60.0)

    time.sleep(3.0)

    deploys = kubectl_run("get", "deploy", "-o", "name").stdout
    leftover_deploys = [line for line in deploys.splitlines() if "-sb-e2e-" in line]
    assert leftover_deploys == []

    virtual_services = json.loads(kubectl_run("get", "vs", "-o", "json").stdout)
    route_names = [
        http_route.get("name", "")
        for item in virtual_services.get("items", [])
        for http_route in (item.get("spec", {}).get("http") or [])
    ]
    leftover_routes = [name for name in route_names if "e2e-" in name]
    assert leftover_routes == []

    mock_rules = client.get("/mocks/rules").json()
    leftover_rules = [rule for rule in mock_rules if rule["sandbox_id"] in names]
    assert leftover_rules == []
