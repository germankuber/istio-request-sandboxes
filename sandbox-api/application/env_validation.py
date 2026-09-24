import re

ENV_VAR_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_env_var_name(name: str) -> None:
    if not ENV_VAR_NAME_PATTERN.match(name):
        raise ValueError(
            f"env var name '{name}' must match {ENV_VAR_NAME_PATTERN.pattern}: start with a "
            "letter or underscore, followed by letters, digits, or underscores"
        )
