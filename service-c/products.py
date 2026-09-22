import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://poc:poc@postgres-baseline:5432/catalog")


def fetch_products_legacy() -> list[dict]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT id, name, price_cents, stock FROM products ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_products_split() -> list[dict]:
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT id, brand, model, price_cents, stock FROM products ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]
