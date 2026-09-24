from typing import cast

import pytest
from kubernetes.client import CustomObjectsApi
from kubernetes.client.rest import ApiException

from infrastructure.k8s_gateway import K8sGateway, _replace_with_conflict_retry


class _FakeCustomObjectsApi:
    def __init__(self, items: list[dict]) -> None:
        self._items = items
        self.calls: list[tuple[str, str, str, str]] = []

    def list_namespaced_custom_object(self, group: str, version: str, namespace: str, plural: str) -> dict:
        self.calls.append((group, version, namespace, plural))
        return {"items": self._items}


def _make_gateway(custom: _FakeCustomObjectsApi) -> K8sGateway:
    gateway = K8sGateway.__new__(K8sGateway)
    gateway._namespace = "default"
    gateway._custom = cast(CustomObjectsApi, custom)
    return gateway


def test_replace_with_conflict_retry_refetches_and_succeeds_after_conflicts() -> None:
    replace_calls: list[dict] = []
    get_calls: list[int] = []
    resource_versions = iter(["2", "3"])

    def get_fn() -> dict:
        get_calls.append(1)
        return {"metadata": {"resourceVersion": next(resource_versions)}}

    attempts = {"count": 0}

    def replace_fn(manifest: dict) -> None:
        replace_calls.append(manifest)
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ApiException(status=409)

    manifest = {"metadata": {"name": "service-c", "resourceVersion": "1"}}

    _replace_with_conflict_retry(get_fn, replace_fn, manifest)

    assert len(replace_calls) == 3
    assert len(get_calls) == 2
    assert replace_calls[1]["metadata"]["resourceVersion"] == "2"
    assert replace_calls[2]["metadata"]["resourceVersion"] == "3"


def test_replace_with_conflict_retry_raises_after_max_attempts() -> None:
    def get_fn() -> dict:
        return {"metadata": {"resourceVersion": "99"}}

    def replace_fn(manifest: dict) -> None:
        raise ApiException(status=409)

    manifest = {"metadata": {"name": "service-c", "resourceVersion": "1"}}

    with pytest.raises(ApiException):
        _replace_with_conflict_retry(get_fn, replace_fn, manifest, max_attempts=3)


def test_replace_with_conflict_retry_raises_immediately_on_non_conflict_error() -> None:
    def get_fn() -> dict:
        raise AssertionError("should not be called")

    def replace_fn(manifest: dict) -> None:
        raise ApiException(status=500)

    manifest = {"metadata": {"name": "service-c", "resourceVersion": "1"}}

    with pytest.raises(ApiException):
        _replace_with_conflict_retry(get_fn, replace_fn, manifest)


def test_known_sandbox_ids_returns_every_cr_name() -> None:
    custom = _FakeCustomObjectsApi(
        [
            {"metadata": {"name": "sandbox-a-1"}},
            {"metadata": {"name": "test-123"}},
        ]
    )
    gateway = _make_gateway(custom)

    result = gateway.known_sandbox_ids()

    assert result == frozenset({"sandbox-a-1", "test-123"})


def test_known_sandbox_ids_includes_cr_pending_deletion() -> None:
    custom = _FakeCustomObjectsApi(
        [{"metadata": {"name": "test-123", "deletionTimestamp": "2024-01-01T00:00:00Z"}}]
    )
    gateway = _make_gateway(custom)

    result = gateway.known_sandbox_ids()

    assert result == frozenset({"test-123"})


def test_known_sandbox_ids_returns_empty_frozenset_when_no_sandboxes_exist() -> None:
    gateway = _make_gateway(_FakeCustomObjectsApi([]))

    assert gateway.known_sandbox_ids() == frozenset()
