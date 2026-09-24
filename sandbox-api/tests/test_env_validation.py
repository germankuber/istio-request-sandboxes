import pytest

from application.env_validation import validate_env_var_name


@pytest.mark.parametrize("name", ["DATABASE_URL", "_private", "a", "A1", "LOG_LEVEL", "_"])
def test_valid_env_names_pass(name: str) -> None:
    validate_env_var_name(name)


@pytest.mark.parametrize(
    "name",
    ["1START", "has-dash", "has space", "", "has.dot", "2FA", "-leading"],
)
def test_invalid_env_names_raise(name: str) -> None:
    with pytest.raises(ValueError):
        validate_env_var_name(name)
