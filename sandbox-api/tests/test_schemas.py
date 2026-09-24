import pytest
from pydantic import ValidationError

from api.schemas import EnvVarRequest, ServiceCreateRequest


def test_service_create_request_accepts_matching_image() -> None:
    request = ServiceCreateRequest(name="service-d", image="service-d:pr-42")

    assert request.image == "service-d:pr-42"


def test_service_create_request_rejects_wrong_repository_image() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ServiceCreateRequest(name="service-d", image="evil/registry:latest")

    message = str(exc_info.value)
    assert "service-d" in message
    assert "evil/registry:latest" in message


def test_service_create_request_rejects_other_services_own_image() -> None:
    with pytest.raises(ValidationError):
        ServiceCreateRequest(name="service-d", image="service-c:latest")


def test_service_create_request_allows_missing_image() -> None:
    request = ServiceCreateRequest(name="service-d")

    assert request.image is None


def test_env_var_request_accepts_valid_name() -> None:
    request = EnvVarRequest(name="LOG_LEVEL", value="debug")

    assert request.name == "LOG_LEVEL"


def test_env_var_request_rejects_name_starting_with_digit() -> None:
    with pytest.raises(ValidationError):
        EnvVarRequest(name="1BAD", value="x")


def test_env_var_request_rejects_name_with_dash() -> None:
    with pytest.raises(ValidationError):
        EnvVarRequest(name="BAD-NAME", value="x")


def test_env_var_request_rejects_name_with_space() -> None:
    with pytest.raises(ValidationError):
        EnvVarRequest(name="BAD NAME", value="x")
