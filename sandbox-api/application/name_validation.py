import re

DNS1123_MAX_LENGTH = 63
_DNS1123_PATTERN = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


def validate_sandbox_name(name: str) -> None:
    if len(name) == 0 or len(name) > DNS1123_MAX_LENGTH:
        raise ValueError(f"sandbox name must be 1-{DNS1123_MAX_LENGTH} characters long")
    if not _DNS1123_PATTERN.match(name):
        raise ValueError(
            "sandbox name must be a valid DNS-1123 label: lowercase alphanumeric characters "
            "or '-', starting and ending with an alphanumeric character"
        )
