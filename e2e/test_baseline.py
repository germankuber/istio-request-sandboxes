import httpx


def test_headerless_request_routes_to_baseline_everywhere(chain_json, mock_proxy_admin_url):
    httpx.delete(f"{mock_proxy_admin_url}/__admin/requests", timeout=5.0)
    response = chain_json(None)
    downstream = response["downstream"]["downstream"]
    assert response["version"] == "baseline"
    assert response["downstream"]["version"] == "baseline"
    assert downstream["c"]["version"] == "baseline"
    assert downstream["d"]["version"] == "baseline"
    assert downstream["e"]["version"] == "baseline"
    assert downstream["d"]["external"]["payments"]["mocked"] is False
    assert downstream["d"]["external"]["weather"]["mocked"] is False


def test_headerless_requests_never_reach_mock_proxy(chain_json, mock_proxy_admin_url):
    httpx.delete(f"{mock_proxy_admin_url}/__admin/requests", timeout=5.0)
    chain_json(None)
    journal = httpx.get(f"{mock_proxy_admin_url}/__admin/requests", timeout=5.0).json()
    assert len(journal["requests"]) == 0


def test_unknown_sandbox_header_routes_to_baseline(chain_json):
    response = chain_json("e2e-nope")
    downstream = response["downstream"]["downstream"]
    assert downstream["c"]["version"] == "baseline"
    assert downstream["d"]["version"] == "baseline"
    assert downstream["e"]["version"] == "baseline"
    assert downstream["d"]["external"]["payments"]["mocked"] is False
    assert downstream["d"]["external"]["weather"]["mocked"] is False
