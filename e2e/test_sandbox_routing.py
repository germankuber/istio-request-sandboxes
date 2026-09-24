def test_single_sandbox_routes_service_c_and_d_with_mocked_payment(
    sandbox_factory, wait_for_phase, chain_json
):
    payload = {
        "name": "e2e-cd",
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
            }
        ],
    }
    response = sandbox_factory(payload)
    assert response.status_code == 201, response.text
    assert wait_for_phase("e2e-cd", "Ready", 120)

    sandboxed = chain_json("e2e-cd")
    downstream = sandboxed["downstream"]["downstream"]
    assert downstream["c"]["version"] == "e2e-cd"
    assert downstream["d"]["version"] == "e2e-cd"
    assert downstream["e"]["version"] == "baseline"
    assert downstream["d"]["external"]["payments"]["mocked"] is True
    assert downstream["d"]["external"]["payments"]["http_status"] == 402
    assert downstream["d"]["external"]["weather"]["mocked"] is False

    headerless = chain_json(None)
    headerless_downstream = headerless["downstream"]["downstream"]
    assert headerless_downstream["c"]["version"] == "baseline"
    assert headerless_downstream["d"]["version"] == "baseline"


def test_headerless_requests_never_leak_into_sandbox_routing(
    sandbox_factory, wait_for_phase, chain_json
):
    payload = {"name": "e2e-a", "services": [{"name": "service-a"}], "mocks": []}
    response = sandbox_factory(payload)
    assert response.status_code == 201, response.text
    assert wait_for_phase("e2e-a", "Ready", 90)

    sandboxed = chain_json("e2e-a")
    assert sandboxed["version"] == "e2e-a"

    leaks = 0
    for _ in range(20):
        headerless = chain_json(None)
        if headerless["version"] != "baseline":
            leaks += 1
    assert leaks == 0


def test_two_sandboxes_on_same_service_do_not_cross_talk(
    sandbox_factory, wait_for_phase, chain_json
):
    payload_c1 = {
        "name": "e2e-c1",
        "services": [{"name": "service-c", "use_migrated_db": True}],
        "mocks": [],
    }
    payload_c2 = {
        "name": "e2e-c2",
        "services": [{"name": "service-c", "use_migrated_db": True}],
        "mocks": [],
    }
    response_c1 = sandbox_factory(payload_c1)
    response_c2 = sandbox_factory(payload_c2)
    assert response_c1.status_code == 201, response_c1.text
    assert response_c2.status_code == 201, response_c2.text
    assert wait_for_phase("e2e-c1", "Ready", 120)
    assert wait_for_phase("e2e-c2", "Ready", 120)

    crosstalk = 0
    for i in range(1, 21):
        header = "e2e-c1" if i % 2 == 0 else "e2e-c2"
        response = chain_json(header)
        version = response["downstream"]["downstream"]["c"]["version"]
        if version != header:
            crosstalk += 1
    assert crosstalk == 0
