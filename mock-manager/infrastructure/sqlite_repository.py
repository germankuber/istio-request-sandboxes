import json
import sqlite3
from pathlib import Path

from domain.rule import ExternalHost, Rule

BUSY_TIMEOUT_SECONDS = 5.0


class SqliteRuleRepository:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._init_schema()

    def list_all(self) -> list[Rule]:
        with self._connect() as connection:
            rows = connection.execute("SELECT payload FROM rules").fetchall()
        return [self._deserialize(row[0]) for row in rows]

    def get(self, rule_id: str) -> Rule | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM rules WHERE id = ?", (rule_id,)
            ).fetchone()
        return self._deserialize(row[0]) if row else None

    def find_by_key(
        self, sandbox_id: str, host: ExternalHost, method: str, path: str
    ) -> Rule | None:
        for rule in self.list_all():
            if (
                rule.sandbox_id == sandbox_id
                and rule.host == host
                and rule.method == method
                and rule.path == path
            ):
                return rule
        return None

    def save(self, rule: Rule) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO rules (id, payload) VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (rule.id, self._serialize(rule)),
            )

    def delete(self, rule_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM rules WHERE id = ?", (rule_id,))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path, timeout=BUSY_TIMEOUT_SECONDS)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS rules (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    @staticmethod
    def _serialize(rule: Rule) -> str:
        return json.dumps(
            {
                "id": rule.id,
                "sandbox_id": rule.sandbox_id,
                "host": rule.host.value,
                "method": rule.method,
                "path": rule.path,
                "status": rule.status,
                "headers": rule.headers,
                "body": rule.body,
                "delay_ms": rule.delay_ms,
                "enabled": rule.enabled,
            }
        )

    @staticmethod
    def _deserialize(payload: str) -> Rule:
        data = json.loads(payload)
        return Rule(
            id=data["id"],
            sandbox_id=data["sandbox_id"],
            host=ExternalHost(data["host"]),
            method=data["method"],
            path=data["path"],
            status=data["status"],
            headers=data["headers"],
            body=data["body"],
            delay_ms=data["delay_ms"],
            enabled=data["enabled"],
        )
