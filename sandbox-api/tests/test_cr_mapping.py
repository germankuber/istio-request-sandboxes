from application.cr_mapping import build_sandbox_cr
from domain.sandbox import EnvVar, MockRequest, ServiceRequest


def test_build_sandbox_cr_matches_test_123_shape() -> None:
    services = (
        ServiceRequest(
            name="service-c",
            image=None,
            env=(),
            use_migrated_db=True,
        ),
    )
    mocks = (
        MockRequest(
            host="external-payments",
            method="POST",
            path="/charge",
            status=402,
            body={"error": "card_declined"},
            enabled=True,
        ),
    )

    cr = build_sandbox_cr("test-123", services, mocks)

    assert cr["apiVersion"] == "sandbox.poc/v1"
    assert cr["kind"] == "Sandbox"
    assert cr["metadata"]["name"] == "test-123"
    assert cr["spec"]["services"] == [
        {
            "name": "service-c",
            "env": [
                {"name": "DATABASE_URL", "value": "postgresql://poc:poc@postgres-sandbox:5432/catalog"},
                {"name": "DB_PEER_SERVICE", "value": "postgres-sandbox"},
                {"name": "DB_SCHEMA", "value": "split"},
            ],
        }
    ]
    assert cr["spec"]["mocks"] == [
        {
            "host": "external-payments",
            "method": "POST",
            "path": "/charge",
            "status": 402,
            "enabled": True,
            "body": {"error": "card_declined"},
        }
    ]


def test_build_sandbox_cr_includes_image_override_when_present() -> None:
    services = (
        ServiceRequest(name="service-d", image="service-d:pr-42", env=(), use_migrated_db=False),
    )

    cr = build_sandbox_cr("demo", services, ())

    assert cr["spec"]["services"] == [{"name": "service-d", "image": "service-d:pr-42"}]


def test_build_sandbox_cr_omits_env_when_empty_and_not_migrated() -> None:
    services = (ServiceRequest(name="service-d", image=None, env=(), use_migrated_db=False),)

    cr = build_sandbox_cr("demo", services, ())

    assert cr["spec"]["services"] == [{"name": "service-d"}]


def test_build_sandbox_cr_keeps_explicit_env_for_non_db_service() -> None:
    services = (
        ServiceRequest(
            name="service-d",
            image=None,
            env=(EnvVar(name="LOG_LEVEL", value="debug"),),
            use_migrated_db=False,
        ),
    )

    cr = build_sandbox_cr("demo", services, ())

    assert cr["spec"]["services"] == [
        {"name": "service-d", "env": [{"name": "LOG_LEVEL", "value": "debug"}]}
    ]


def test_build_sandbox_cr_with_no_services_or_mocks() -> None:
    cr = build_sandbox_cr("empty", (), ())

    assert cr["spec"] == {"services": [], "mocks": []}
