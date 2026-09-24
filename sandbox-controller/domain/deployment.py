import copy

from domain.models import Sandbox, ServiceOverride

DEPLOYMENT_MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
DEPLOYMENT_MANAGED_BY_VALUE = "sandbox-controller"
SANDBOX_ID_LABEL = "sandbox.poc/sandbox-id"
VERSION_ENV_NAME = "VERSION"


def sandbox_deployment_name(service_name: str, sandbox_id: str) -> str:
    return f"{service_name}-sb-{sandbox_id}"


def build_sandbox_deployment(baseline_deployment: dict, sandbox: Sandbox, service: ServiceOverride) -> dict:
    name = sandbox_deployment_name(service.name, sandbox.sandbox_id)
    labels = {
        "app": service.name,
        "version": sandbox.sandbox_id,
        DEPLOYMENT_MANAGED_BY_LABEL: DEPLOYMENT_MANAGED_BY_VALUE,
        SANDBOX_ID_LABEL: sandbox.sandbox_id,
    }
    pod_spec = _cloned_pod_spec(baseline_deployment)
    pod_spec["containers"][0] = _merged_container(pod_spec["containers"][0], sandbox, service)
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": service.name, "version": sandbox.sandbox_id}},
            "template": {"metadata": {"labels": labels}, "spec": pod_spec},
        },
    }


def _cloned_pod_spec(baseline_deployment: dict) -> dict:
    return copy.deepcopy(baseline_deployment["spec"]["template"]["spec"])


def _merged_container(container: dict, sandbox: Sandbox, service: ServiceOverride) -> dict:
    merged = dict(container)
    if service.image:
        merged["image"] = service.image
    merged["env"] = _merged_env(container.get("env", []), sandbox, service)
    return merged


def _merged_env(baseline_env: list[dict], sandbox: Sandbox, service: ServiceOverride) -> list[dict]:
    overrides = {override.name: override.value for override in service.env}
    overrides[VERSION_ENV_NAME] = sandbox.sandbox_id

    merged: list[dict] = []
    applied: set[str] = set()
    for entry in baseline_env:
        entry_name = entry["name"]
        if entry_name in overrides:
            merged.append({"name": entry_name, "value": overrides[entry_name]})
            applied.add(entry_name)
        else:
            merged.append(dict(entry))

    for override_name, override_value in overrides.items():
        if override_name not in applied:
            merged.append({"name": override_name, "value": override_value})

    return merged
