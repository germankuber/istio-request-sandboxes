from typing import Callable, cast

import kubernetes.client as k8s_client
import kubernetes.config as k8s_config
from kubernetes.client.rest import ApiException

from domain.deployment import sandbox_deployment_name
from domain.models import Sandbox, SandboxRouteTarget

NAMESPACE = "default"
CONFLICT_STATUS_CODE = 409
MAX_CONFLICT_RETRY_ATTEMPTS = 3
ISTIO_GROUP = "networking.istio.io"
ISTIO_VERSION = "v1"
DESTINATION_RULE_PLURAL = "destinationrules"
VIRTUAL_SERVICE_PLURAL = "virtualservices"
SANDBOX_GROUP = "sandbox.poc"
SANDBOX_VERSION = "v1"
SANDBOX_PLURAL = "sandboxes"
DEPLOYMENT_MANAGED_BY_LABEL = "app.kubernetes.io/managed-by"
DEPLOYMENT_MANAGED_BY_VALUE = "sandbox-controller"
SANDBOX_ID_LABEL = "sandbox.poc/sandbox-id"
SANDBOX_KIND = "Sandbox"
SANDBOX_API_VERSION = f"{SANDBOX_GROUP}/{SANDBOX_VERSION}"


class K8sGateway:
    def __init__(self, namespace: str = NAMESPACE) -> None:
        _load_kube_config()
        self._namespace = namespace
        self._apps = k8s_client.AppsV1Api()
        self._custom = k8s_client.CustomObjectsApi()

    def get_baseline(self, service_name: str) -> dict:
        deployment = self._apps.read_namespaced_deployment(f"{service_name}-baseline", self._namespace)
        return cast(dict, k8s_client.ApiClient().sanitize_for_serialization(deployment))

    def apply_sandbox_deployment(self, manifest: dict, owner: Sandbox) -> None:
        manifest = dict(manifest)
        manifest["metadata"] = {
            **manifest["metadata"],
            "ownerReferences": [_owner_reference(owner)],
        }
        name = manifest["metadata"]["name"]
        try:
            self._apps.replace_namespaced_deployment(name, self._namespace, manifest)
        except ApiException as error:
            if error.status != 404:
                raise
            self._apps.create_namespaced_deployment(self._namespace, manifest)

    def delete_sandbox_deployment(self, service_name: str, sandbox_id: str) -> None:
        name = sandbox_deployment_name(service_name, sandbox_id)
        _ignore_404(lambda: self._apps.delete_namespaced_deployment(name, self._namespace))

    def list_managed_service_names(self, sandbox_id: str) -> tuple[str, ...]:
        selector = f"{DEPLOYMENT_MANAGED_BY_LABEL}={DEPLOYMENT_MANAGED_BY_VALUE},{SANDBOX_ID_LABEL}={sandbox_id}"
        deployments = self._apps.list_namespaced_deployment(self._namespace, label_selector=selector)
        return tuple(item.metadata.labels["app"] for item in deployments.items)

    def is_ready(self, service_name: str, sandbox_id: str) -> bool:
        name = sandbox_deployment_name(service_name, sandbox_id)
        try:
            deployment = cast(
                k8s_client.V1Deployment, self._apps.read_namespaced_deployment_status(name, self._namespace)
            )
        except ApiException as error:
            if error.status == 404:
                return False
            raise
        status = deployment.status
        if status is None:
            return False
        return (status.available_replicas or 0) >= 1

    def route_targets(self, service_name: str) -> tuple[SandboxRouteTarget, ...]:
        sandboxes = self._custom.list_namespaced_custom_object(
            SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL
        )
        targets: list[SandboxRouteTarget] = []
        for item in sandboxes.get("items", []):
            if item.get("metadata", {}).get("deletionTimestamp"):
                continue
            sandbox_id = item["metadata"]["name"]
            service_names = {entry["name"] for entry in item.get("spec", {}).get("services", [])}
            if service_name not in service_names:
                continue
            targets.append(SandboxRouteTarget(sandbox_id=sandbox_id, ready=self.is_ready(service_name, sandbox_id)))
        return tuple(targets)

    def known_service_names(self) -> set[str]:
        sandboxes = self._custom.list_namespaced_custom_object(
            SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL
        )
        names: set[str] = set()
        for item in sandboxes.get("items", []):
            names.update(entry["name"] for entry in item.get("spec", {}).get("services", []))
        return names

    def known_sandbox_ids(self) -> frozenset[str]:
        sandboxes = self._custom.list_namespaced_custom_object(
            SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL
        )
        return frozenset(item["metadata"]["name"] for item in sandboxes.get("items", []))

    def apply_destination_rule(self, manifest: dict) -> None:
        self._apply_custom(ISTIO_GROUP, ISTIO_VERSION, DESTINATION_RULE_PLURAL, manifest)

    def apply_virtual_service(self, manifest: dict) -> None:
        self._apply_custom(ISTIO_GROUP, ISTIO_VERSION, VIRTUAL_SERVICE_PLURAL, manifest)

    def delete_destination_rule(self, service_name: str) -> None:
        self._delete_custom(ISTIO_GROUP, ISTIO_VERSION, DESTINATION_RULE_PLURAL, service_name)

    def delete_virtual_service(self, service_name: str) -> None:
        self._delete_custom(ISTIO_GROUP, ISTIO_VERSION, VIRTUAL_SERVICE_PLURAL, service_name)

    def _apply_custom(self, group: str, version: str, plural: str, manifest: dict) -> None:
        name = manifest["metadata"]["name"]
        try:
            existing = cast(
                dict, self._custom.get_namespaced_custom_object(group, version, self._namespace, plural, name)
            )
        except ApiException as error:
            if error.status != 404:
                raise
            self._custom.create_namespaced_custom_object(group, version, self._namespace, plural, manifest)
            return

        versioned_manifest = dict(manifest)
        versioned_manifest["metadata"] = {
            **manifest["metadata"],
            "resourceVersion": existing["metadata"]["resourceVersion"],
        }

        def get_fn() -> dict:
            return cast(dict, self._custom.get_namespaced_custom_object(group, version, self._namespace, plural, name))

        def replace_fn(current_manifest: dict) -> None:
            self._custom.replace_namespaced_custom_object(
                group, version, self._namespace, plural, name, current_manifest
            )

        _replace_with_conflict_retry(get_fn, replace_fn, versioned_manifest)

    def _delete_custom(self, group: str, version: str, plural: str, name: str) -> None:
        _ignore_404(lambda: self._custom.delete_namespaced_custom_object(group, version, self._namespace, plural, name))


def _load_kube_config() -> None:
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()


def _owner_reference(owner: Sandbox) -> dict:
    return {
        "apiVersion": SANDBOX_API_VERSION,
        "kind": SANDBOX_KIND,
        "name": owner.sandbox_id,
        "uid": owner.uid,
        "controller": True,
        "blockOwnerDeletion": True,
    }


def _ignore_404(call) -> None:
    try:
        call()
    except ApiException as error:
        if error.status != 404:
            raise


def _replace_with_conflict_retry(
    get_fn: Callable[[], dict],
    replace_fn: Callable[[dict], None],
    manifest: dict,
    max_attempts: int = MAX_CONFLICT_RETRY_ATTEMPTS,
) -> None:
    current_manifest = manifest
    for attempt in range(1, max_attempts + 1):
        try:
            replace_fn(current_manifest)
            return
        except ApiException as error:
            if error.status != CONFLICT_STATUS_CODE or attempt == max_attempts:
                raise
            fresh = get_fn()
            current_manifest = dict(current_manifest)
            current_manifest["metadata"] = {
                **current_manifest["metadata"],
                "resourceVersion": fresh["metadata"]["resourceVersion"],
            }
