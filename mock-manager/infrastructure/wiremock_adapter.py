import httpx

from domain.stub import WireMockStub

MANAGED_BY = "mock-manager"


class WireMockAdapter:
    def __init__(self, admin_base_url: str, timeout: float = 5.0) -> None:
        self._admin_base_url = admin_base_url.rstrip("/")
        self._timeout = timeout

    def list_managed_stub_ids(self) -> set[str]:
        response = httpx.get(f"{self._admin_base_url}/mappings", timeout=self._timeout)
        response.raise_for_status()
        mappings = response.json().get("mappings", [])
        return {
            mapping["id"]
            for mapping in mappings
            if mapping.get("metadata", {}).get("managed_by") == MANAGED_BY
        }

    def upsert(self, stub: WireMockStub) -> None:
        body = self._to_wiremock_body(stub)
        response = httpx.put(
            f"{self._admin_base_url}/mappings/{stub.id}", json=body, timeout=self._timeout
        )
        if response.status_code == 404:
            response = httpx.post(
                f"{self._admin_base_url}/mappings", json=body, timeout=self._timeout
            )
        response.raise_for_status()

    def delete(self, stub_id: str) -> None:
        response = httpx.delete(
            f"{self._admin_base_url}/mappings/{stub_id}", timeout=self._timeout
        )
        if response.status_code != 404:
            response.raise_for_status()

    @staticmethod
    def _to_wiremock_body(stub: WireMockStub) -> dict[str, object]:
        return {
            "id": stub.id,
            "priority": stub.priority,
            "metadata": {"managed_by": MANAGED_BY, "rule_id": stub.rule_id},
            "request": {
                "method": stub.method,
                "urlPath": stub.url_path,
                "host": {"contains": stub.host_contains},
                "headers": {stub.header_name: {"equalTo": stub.header_equal_to}},
            },
            "response": {
                "status": stub.status,
                "headers": stub.headers,
                "jsonBody": stub.body,
                "fixedDelayMilliseconds": stub.delay_ms,
            },
        }
