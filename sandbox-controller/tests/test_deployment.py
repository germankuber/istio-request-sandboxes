from domain.deployment import (
    DEPLOYMENT_MANAGED_BY_LABEL,
    DEPLOYMENT_MANAGED_BY_VALUE,
    SANDBOX_ID_LABEL,
    build_sandbox_deployment,
    sandbox_deployment_name,
)
from domain.models import EnvOverride, Sandbox, ServiceOverride

BASELINE_DEPLOYMENT = {
    "apiVersion": "apps/v1",
    "kind": "Deployment",
    "metadata": {"name": "service-c-baseline"},
    "spec": {
        "replicas": 1,
        "template": {
            "metadata": {"labels": {"app": "service-c", "version": "baseline"}},
            "spec": {
                "containers": [
                    {
                        "name": "service-c",
                        "image": "service-c:latest",
                        "ports": [{"containerPort": 8000}],
                        "env": [
                            {"name": "VERSION", "value": "baseline"},
                            {
                                "name": "DATABASE_URL",
                                "value": "postgresql://poc:poc@postgres-baseline:5432/catalog",
                            },
                            {"name": "DB_PEER_SERVICE", "value": "postgres-baseline"},
                        ],
                    }
                ]
            },
        },
    },
}


def make_sandbox(service: ServiceOverride) -> Sandbox:
    return Sandbox(sandbox_id="test-123", services=(service,), mocks=())


def test_sandbox_deployment_name_is_prefixed_with_service_and_sandbox() -> None:
    assert sandbox_deployment_name("service-c", "test-123") == "service-c-sb-test-123"


def test_build_sandbox_deployment_sets_labels_and_selector() -> None:
    service = ServiceOverride(name="service-c")
    manifest = build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    assert manifest["metadata"]["name"] == "service-c-sb-test-123"
    assert manifest["metadata"]["labels"]["app"] == "service-c"
    assert manifest["metadata"]["labels"]["version"] == "test-123"
    assert manifest["metadata"]["labels"][DEPLOYMENT_MANAGED_BY_LABEL] == DEPLOYMENT_MANAGED_BY_VALUE
    assert manifest["metadata"]["labels"][SANDBOX_ID_LABEL] == "test-123"
    assert manifest["spec"]["selector"]["matchLabels"] == {"app": "service-c", "version": "test-123"}
    assert manifest["spec"]["template"]["metadata"]["labels"] == manifest["metadata"]["labels"]


def test_build_sandbox_deployment_overrides_version_env_to_sandbox_id() -> None:
    service = ServiceOverride(name="service-c")
    manifest = build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    env = {entry["name"]: entry["value"] for entry in manifest["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["VERSION"] == "test-123"


def test_build_sandbox_deployment_keeps_baseline_image_when_not_overridden() -> None:
    service = ServiceOverride(name="service-c")
    manifest = build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    assert manifest["spec"]["template"]["spec"]["containers"][0]["image"] == "service-c:latest"


def test_build_sandbox_deployment_applies_image_override() -> None:
    service = ServiceOverride(name="service-c", image="service-c:pr-42")
    manifest = build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    assert manifest["spec"]["template"]["spec"]["containers"][0]["image"] == "service-c:pr-42"


def test_build_sandbox_deployment_merges_env_overrides_onto_baseline() -> None:
    service = ServiceOverride(
        name="service-c",
        env=(
            EnvOverride(name="DATABASE_URL", value="postgresql://poc:poc@postgres-sandbox:5432/catalog"),
            EnvOverride(name="DB_PEER_SERVICE", value="postgres-sandbox"),
        ),
    )
    manifest = build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    env = {entry["name"]: entry["value"] for entry in manifest["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["DATABASE_URL"] == "postgresql://poc:poc@postgres-sandbox:5432/catalog"
    assert env["DB_PEER_SERVICE"] == "postgres-sandbox"
    assert env["VERSION"] == "test-123"


def test_build_sandbox_deployment_adds_env_override_not_present_in_baseline() -> None:
    service = ServiceOverride(name="service-c", env=(EnvOverride(name="FEATURE_FLAG", value="on"),))
    manifest = build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    env = {entry["name"]: entry["value"] for entry in manifest["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["FEATURE_FLAG"] == "on"


def test_build_sandbox_deployment_does_not_mutate_baseline_input() -> None:
    import copy

    baseline_copy = copy.deepcopy(BASELINE_DEPLOYMENT)
    service = ServiceOverride(name="service-c", env=(EnvOverride(name="DATABASE_URL", value="changed"),))
    build_sandbox_deployment(BASELINE_DEPLOYMENT, make_sandbox(service), service)

    assert BASELINE_DEPLOYMENT == baseline_copy
