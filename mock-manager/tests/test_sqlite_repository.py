import sqlite3

from domain.rule import ExternalHost, Rule, RuleBody
from infrastructure.sqlite_repository import SqliteRuleRepository


def make_rule(
    sandbox_id: str = "test-123",
    host: ExternalHost = ExternalHost.PAYMENTS,
    method: str = "post",
    path: str = "/charge",
    status: int = 402,
    headers: dict[str, str] | None = None,
    body: RuleBody = None,
    delay_ms: int = 0,
    enabled: bool = True,
) -> Rule:
    return Rule.new(
        sandbox_id=sandbox_id,
        host=host,
        method=method,
        path=path,
        status=status,
        headers=headers if headers is not None else {},
        body=body,
        delay_ms=delay_ms,
        enabled=enabled,
    )


def test_repository_enables_wal_mode(tmp_path) -> None:
    db_path = str(tmp_path / "rules.db")

    SqliteRuleRepository(db_path)

    connection = sqlite3.connect(db_path)
    try:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        connection.close()
    assert mode.lower() == "wal"


def test_find_by_key_returns_matching_rule(tmp_path) -> None:
    repository = SqliteRuleRepository(str(tmp_path / "rules.db"))
    rule = make_rule()
    repository.save(rule)

    found = repository.find_by_key(rule.sandbox_id, rule.host, rule.method, rule.path)

    assert found is not None
    assert found.id == rule.id


def test_find_by_key_returns_none_when_no_match(tmp_path) -> None:
    repository = SqliteRuleRepository(str(tmp_path / "rules.db"))

    found = repository.find_by_key("test-123", ExternalHost.PAYMENTS, "POST", "/charge")

    assert found is None
