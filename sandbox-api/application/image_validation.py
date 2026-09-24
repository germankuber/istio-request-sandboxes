import re

IMAGE_TAG_PATTERN = r"[A-Za-z0-9._-]{1,128}"


def validate_service_image(service_name: str, image: str) -> None:
    pattern = re.compile(rf"^{re.escape(service_name)}:{IMAGE_TAG_PATTERN}$")
    if not pattern.match(image):
        raise ValueError(
            f"image override for service '{service_name}' must reference that service's own "
            f"repository, matching '{service_name}:<tag>'; got '{image}'"
        )
