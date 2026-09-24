import os
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx
import pytest

DEFAULT_BASE_URL = "http://localhost:8081"
DEFAULT_KUBE_CONTEXT = "colima-sandbox-poc"
DEFAULT_MOCK_PROXY_LOCAL_PORT = 18090


@dataclass(frozen=True)
class SandboxSnapshot:
    phase: str
    generation: str
    resource_version: str


def _kubectl(context: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["kubectl", "--context", context, *args],
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def _kubectl_jsonpath(context: str, resource: str, name: str, jsonpath: str) -> str:
    result = _kubectl(context, "get", resource, name, "-o", f"jsonpath={jsonpath}", check=False)
    return result.stdout.strip()


def _read_sandbox_snapshot(context: str, name: str) -> SandboxSnapshot:
    return SandboxSnapshot(
        phase=_kubectl_jsonpath(context, "sandbox", name, "{.status.phase}"),
        generation=_kubectl_jsonpath(context, "sandbox", name, "{.metadata.generation}"),
        resource_version=_kubectl_jsonpath(
            context, "sandbox", name, "{.metadata.resourceVersion}"
        ),
    )


EVENTUALLY_POLL_SECONDS = 1.0


@pytest.fixture
def eventually() -> Callable[[Callable[[], bool], float], bool]:
    def _poll(predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if predicate():
                    return True
            except (httpx.HTTPError, KeyError):
                pass
            time.sleep(EVENTUALLY_POLL_SECONDS)
        return False

    return _poll


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("E2E_BASE_URL", DEFAULT_BASE_URL)


@pytest.fixture(scope="session")
def kube_context() -> str:
    return os.environ.get("E2E_KUBE_CONTEXT", DEFAULT_KUBE_CONTEXT)


@pytest.fixture(scope="session")
def client(base_url: str) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=base_url, timeout=30.0) as http_client:
        yield http_client


@pytest.fixture
def kubectl_run(
    kube_context: str,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return _kubectl(kube_context, *args, check=check)

    return _run


@pytest.fixture
def wait_for_phase(client: httpx.Client) -> Callable[[str, str, float], bool]:
    def _wait(name: str, phase: str, timeout: float = 90.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = client.get(f"/sandboxes-api/sandboxes/{name}")
            if response.status_code == 200:
                body = response.json()
                if body.get("status", {}).get("phase") == phase:
                    return True
            time.sleep(1.0)
        return False

    return _wait


@pytest.fixture
def wait_until_gone(client: httpx.Client) -> Callable[[str, float], bool]:
    def _wait(name: str, timeout: float = 90.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            response = client.get(f"/sandboxes-api/sandboxes/{name}")
            if response.status_code == 404:
                return True
            time.sleep(1.0)
        return False

    return _wait


@pytest.fixture
def wait_rollout_ready(kube_context: str) -> Callable[[str, float], bool]:
    def _wait(deployment_name: str, timeout: float = 90.0) -> bool:
        result = _kubectl(
            kube_context,
            "rollout",
            "status",
            f"deploy/{deployment_name}",
            f"--timeout={int(timeout)}s",
            check=False,
        )
        return result.returncode == 0

    return _wait


@pytest.fixture
def sandbox_factory(
    client: httpx.Client,
    wait_until_gone: Callable[[str, float], bool],
) -> Iterator[Callable[[dict], httpx.Response]]:
    created: list[str] = []

    def _create(payload: dict) -> httpx.Response:
        response = client.post("/sandboxes-api/sandboxes", json=payload)
        if response.status_code == 201:
            created.append(payload["name"])
        return response

    yield _create

    seen: set[str] = set()
    for name in created:
        if name in seen:
            continue
        seen.add(name)
        client.delete(f"/sandboxes-api/sandboxes/{name}")
    for name in seen:
        wait_until_gone(name, 60.0)


@pytest.fixture
def chain_json(client: httpx.Client) -> Callable[[str | None], dict]:
    def _get(sandbox_id: str | None = None) -> dict:
        headers = {"X-Sandbox-ID": sandbox_id} if sandbox_id else {}
        response = client.get("/api/chain", headers=headers)
        response.raise_for_status()
        return response.json()

    return _get


@pytest.fixture(scope="session")
def mock_proxy_admin_url(kube_context: str) -> Iterator[str]:
    local_port = int(os.environ.get("E2E_MOCK_PROXY_LOCAL_PORT", DEFAULT_MOCK_PROXY_LOCAL_PORT))
    admin_url = f"http://localhost:{local_port}"
    process = subprocess.Popen(
        ["kubectl", "--context", kube_context, "port-forward", "svc/mock-proxy", f"{local_port}:80"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15.0
        ready = False
        while time.monotonic() < deadline:
            try:
                httpx.get(admin_url, timeout=1.0)
                ready = True
                break
            except httpx.TransportError:
                time.sleep(0.5)
        if not ready:
            raise RuntimeError("mock-proxy port-forward did not become ready in time")
        yield admin_url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


@pytest.fixture(scope="session", autouse=True)
def sandbox_a_1_snapshot(kube_context: str) -> Iterator[SandboxSnapshot]:
    baseline = _read_sandbox_snapshot(kube_context, "sandbox-a-1")
    yield baseline
    final = _read_sandbox_snapshot(kube_context, "sandbox-a-1")
    assert final.phase == baseline.phase, (
        f"sandbox-a-1 phase changed: {baseline.phase!r} -> {final.phase!r}"
    )
    assert final.generation == baseline.generation, (
        f"sandbox-a-1 generation changed: {baseline.generation!r} -> {final.generation!r}"
    )
    assert final.resource_version == baseline.resource_version, (
        f"sandbox-a-1 resourceVersion changed: "
        f"{baseline.resource_version!r} -> {final.resource_version!r}"
    )
