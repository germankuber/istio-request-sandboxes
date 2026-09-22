#!/usr/bin/env bash
# Seed the baseline database, clone it into the sandbox database, then run the
# sandbox-only migration against the clone. Baseline is never migrated.
set -euo pipefail

KUBECTL="${KUBECTL:-kubectl}"
MIGRATIONS_DIR="$(cd "$(dirname "$0")" && pwd)/migrations"

baseline_pod() { $KUBECTL get pod -l app=postgres,version=baseline -o jsonpath='{.items[0].metadata.name}'; }
sandbox_pod()  { $KUBECTL get pod -l app=postgres,version=sandbox  -o jsonpath='{.items[0].metadata.name}'; }

psql_baseline() { $KUBECTL exec -i "$(baseline_pod)" -c postgres -- psql -U poc -d catalog "$@"; }
psql_sandbox()  { $KUBECTL exec -i "$(sandbox_pod)"  -c postgres -- psql -U poc -d catalog "$@"; }

echo "==> 1. seeding baseline with 001_baseline.sql"
psql_baseline -q < "$MIGRATIONS_DIR/001_baseline.sql"

echo "==> 2. cloning baseline into the sandbox database"
$KUBECTL exec "$(sandbox_pod)" -c postgres -- \
  psql -U poc -d catalog -q -c "DROP TABLE IF EXISTS products CASCADE;"
$KUBECTL exec "$(baseline_pod)" -c postgres -- \
  pg_dump -U poc -d catalog --no-owner | psql_sandbox -q

echo "==> 3. applying 002_split_name_sandbox_only.sql to the SANDBOX clone only"
psql_sandbox -q < "$MIGRATIONS_DIR/002_split_name_sandbox_only.sql"

echo
echo "==> baseline schema (keeps 'name')"
psql_baseline -c "\d products" | head -12

echo
echo "==> sandbox schema (name replaced by brand + model)"
psql_sandbox -c "\d products" | head -12
