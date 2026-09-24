from domain.sandbox import EnvVar

MIGRATED_DB_ENV: tuple[EnvVar, ...] = (
    EnvVar(name="DATABASE_URL", value="postgresql://poc:poc@postgres-sandbox:5432/catalog"),
    EnvVar(name="DB_PEER_SERVICE", value="postgres-sandbox"),
    EnvVar(name="DB_SCHEMA", value="split"),
)


def expand_env(env: tuple[EnvVar, ...], use_migrated_db: bool) -> tuple[EnvVar, ...]:
    if not use_migrated_db:
        return env

    preset_names = {item.name for item in MIGRATED_DB_ENV}
    overrides = {item.name: item.value for item in env if item.name in preset_names}
    extra = tuple(item for item in env if item.name not in preset_names)
    preset = tuple(
        EnvVar(name=item.name, value=overrides.get(item.name, item.value)) for item in MIGRATED_DB_ENV
    )
    return preset + extra
