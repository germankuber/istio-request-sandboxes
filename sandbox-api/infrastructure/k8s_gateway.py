from typing import cast

import kubernetes.client as k8s_client
import kubernetes.config as k8s_config
from kubernetes.client.rest import ApiException

from domain.errors import SandboxAlreadyExistsError, SandboxNotFoundError
from domain.sandbox import BaselineDeployment

NAMESPACE = "default"
SANDBOX_GROUP = "sandbox.poc"
SANDBOX_VERSION = "v1"
SANDBOX_PLURAL = "sandboxes"


class K8sGateway:
    def __init__(self, namespace: str = NAMESPACE) -> None:
        _load_kube_config()
        self._namespace = namespace
        self._apps = k8s_client.AppsV1Api()
        self._custom = k8s_client.CustomObjectsApi()

    def list_sandboxes(self) -> list[dict]:
        result = self._custom.list_namespaced_custom_object(
            SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL
        )
        return list(result.get("items", []))

    def get_sandbox(self, name: str) -> dict | None:
        try:
            result = self._custom.get_namespaced_custom_object(
                SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL, name
            )
            return cast(dict, result)
        except ApiException as error:
            if error.status == 404:
                return None
            raise

    def create_sandbox(self, body: dict) -> dict:
        try:
            return self._custom.create_namespaced_custom_object(
                SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL, body
            )
        except ApiException as error:
            if error.status == 409:
                raise SandboxAlreadyExistsError(body["metadata"]["name"]) from error
            raise

    def delete_sandbox(self, name: str) -> None:
        try:
            self._custom.delete_namespaced_custom_object(
                SANDBOX_GROUP, SANDBOX_VERSION, self._namespace, SANDBOX_PLURAL, name
            )
        except ApiException as error:
            if error.status == 404:
                raise SandboxNotFoundError(name) from error
            raise

    def list_baseline_deployments(self) -> list[BaselineDeployment]:
        deployments = self._apps.list_namespaced_deployment(self._namespace)
        return [
            baseline
            for item in deployments.items
            if (baseline := _to_baseline_deployment(item)) is not None
        ]


def _to_baseline_deployment(item: k8s_client.V1Deployment) -> BaselineDeployment | None:
    spec = item.spec
    if spec is None:
        return None
    template = spec.template
    if template is None:
        return None
    template_labels = (template.metadata.labels if template.metadata else None) or {}
    pod_spec = template.spec
    containers = (pod_spec.containers if pod_spec else None) or []
    env_items = containers[0].env or [] if containers else []
    env = {entry.name: entry.value for entry in env_items if entry.value is not None}
    return BaselineDeployment(
        app=template_labels.get("app", ""),
        version=template_labels.get("version"),
        env=env,
    )


def _load_kube_config() -> None:
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()
