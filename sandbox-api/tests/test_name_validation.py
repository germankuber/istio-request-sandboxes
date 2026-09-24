import pytest

from application.name_validation import validate_sandbox_name


@pytest.mark.parametrize("name", ["test-123", "team-c", "a", "a1", "sandbox-1-demo"])
def test_valid_names_pass(name: str) -> None:
    validate_sandbox_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "Bad_Name",
        "UPPER",
        "-leading-dash",
        "trailing-dash-",
        "has_underscore",
        "has space",
        "a" * 64,
    ],
)
def test_invalid_names_raise(name: str) -> None:
    with pytest.raises(ValueError):
        validate_sandbox_name(name)
