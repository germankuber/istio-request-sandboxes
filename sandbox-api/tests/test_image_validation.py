import pytest

from application.image_validation import validate_service_image


@pytest.mark.parametrize(
    "service_name,image",
    [
        ("service-d", "service-d:latest"),
        ("service-d", "service-d:pr-42"),
        ("service-c", "service-c:1.2.3"),
        ("service-c", "service-c:a"),
    ],
)
def test_valid_images_pass(service_name: str, image: str) -> None:
    validate_service_image(service_name, image)


@pytest.mark.parametrize(
    "service_name,image",
    [
        ("service-d", "evil/registry:latest"),
        ("service-d", "docker.io/foo:latest"),
        ("service-d", "service-c:latest"),
        ("service-d", "service-d"),
        ("service-d", "service-d:"),
        ("service-d", ""),
        ("service-d", "service-dd:latest"),
        ("service-d", "SERVICE-D:latest"),
    ],
)
def test_invalid_images_raise(service_name: str, image: str) -> None:
    with pytest.raises(ValueError):
        validate_service_image(service_name, image)
