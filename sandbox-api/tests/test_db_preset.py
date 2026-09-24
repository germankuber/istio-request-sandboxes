from application.db_preset import MIGRATED_DB_ENV, expand_env
from domain.sandbox import EnvVar


def test_expand_env_returns_original_when_not_using_migrated_db() -> None:
    env = (EnvVar(name="LOG_LEVEL", value="debug"),)

    result = expand_env(env, use_migrated_db=False)

    assert result == env


def test_expand_env_matches_test_123_example_when_using_migrated_db() -> None:
    result = expand_env((), use_migrated_db=True)

    assert result == MIGRATED_DB_ENV
    values = {item.name: item.value for item in result}
    assert values["DATABASE_URL"] == "postgresql://poc:poc@postgres-sandbox:5432/catalog"
    assert values["DB_PEER_SERVICE"] == "postgres-sandbox"
    assert values["DB_SCHEMA"] == "split"


def test_expand_env_keeps_explicit_extra_vars() -> None:
    env = (EnvVar(name="LOG_LEVEL", value="debug"),)

    result = expand_env(env, use_migrated_db=True)

    assert result[-1] == EnvVar(name="LOG_LEVEL", value="debug")
    assert len(result) == len(MIGRATED_DB_ENV) + 1


def test_expand_env_lets_explicit_env_override_preset_value() -> None:
    env = (EnvVar(name="DB_SCHEMA", value="legacy"),)

    result = expand_env(env, use_migrated_db=True)

    values = {item.name: item.value for item in result}
    assert values["DB_SCHEMA"] == "legacy"
    assert len(result) == len(MIGRATED_DB_ENV)
