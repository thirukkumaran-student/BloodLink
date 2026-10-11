#!/usr/bin/env bash
#
# BloodLink — PostgreSQL local setup (owner: D1).
#
# Creates the application + test databases if they are missing, installs the
# PostgreSQL driver if needed, runs the migrations, and prints exactly what to run
# next. Safe to re-run: existing databases and a migrated schema are left alone.
#
#   scripts/setup_postgres.sh
#   scripts/setup_postgres.sh postgresql+psycopg://me:secret@localhost:5432/bloodlink
#   scripts/setup_postgres.sh --env-file /tmp/bloodlink.env     # don't touch .env
#
# Defaults (override by argument or environment):
#   BLOODLINK_DATABASE_URL       postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink
#   BLOODLINK_TEST_DATABASE_URL  …same host/role, database name + "_test"
#
# Requires: psql on PATH, a running PostgreSQL, and credentials allowed to connect.
# Creating a database needs CREATE on the cluster (a superuser, or a role with
# CREATEDB); if that is not permitted the script prints the SQL for your DBA.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

DEFAULT_URL="postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink"
ENV_FILE=".env"
WRITE_ENV=1
ARG_URL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --no-env)   WRITE_ENV=0; shift ;;
    -h|--help)  sed -n '2,20p' "$0"; exit 0 ;;
    *)          ARG_URL="$1"; shift ;;
  esac
done

# Precedence: explicit argument → BLOODLINK_DATABASE_URL → the URL already in the
# env file (so re-running the script keeps using your database) → built-in default.
FILE_URL="$(grep -E '^BLOODLINK_DATABASE_URL=' "$ENV_FILE" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
APP_URL="${ARG_URL:-${BLOODLINK_DATABASE_URL:-${FILE_URL:-$DEFAULT_URL}}}"

say()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗\033[0m %s\n' "$1" >&2; exit 1; }

# `postgresql://` without a driver makes SQLAlchemy reach for psycopg2, which this
# project does not install — normalise to the driver we do install.
case "$APP_URL" in
  postgresql://*) APP_URL="postgresql+psycopg://${APP_URL#postgresql://}" ;;
esac
[[ "$APP_URL" == postgresql+psycopg://* ]] \
  || die "expected a postgresql+psycopg:// URL, got: $APP_URL"

# psql speaks libpq URLs, not SQLAlchemy URLs.
LIBPQ_URL="${APP_URL/postgresql+psycopg/postgresql}"

# Split the URL so we can also talk to the maintenance database.
DB_NAME="${LIBPQ_URL##*/}"
DB_NAME="${DB_NAME%%\?*}"
TEST_URL="${BLOODLINK_TEST_DATABASE_URL:-${LIBPQ_URL%/*}/${DB_NAME}_test}"
TEST_NAME="${TEST_URL##*/}"

say "BloodLink → PostgreSQL setup"
echo "  application database : $LIBPQ_URL"
echo "  test database        : ${TEST_URL/+psycopg/}"

# ---------------------------------------------------------------- prerequisites
say "1. Prerequisites"
command -v psql >/dev/null 2>&1 || die "psql not found on PATH — install the PostgreSQL client package"

if ! python3 -c "import psycopg" >/dev/null 2>&1; then
  warn "psycopg (PostgreSQL driver) is not installed — installing requirements-postgres.txt"
  python3 -m pip install -q -r requirements-postgres.txt \
    || die "could not install the driver; run: pip install -r requirements-postgres.txt"
fi
ok "psycopg available ($(python3 -c 'import psycopg; print(psycopg.__version__)'))"

if ! psql "$LIBPQ_URL" -c 'select 1' >/dev/null 2>&1; then
  warn "cannot connect to $DB_NAME — checking whether it exists"
  if psql "${LIBPQ_URL%/*}/postgres" -c 'select 1' >/dev/null 2>&1; then
    ok "server reachable, database is missing"
    created=0
    for name in "$DB_NAME" "$TEST_NAME"; do
      if psql "${LIBPQ_URL%/*}/postgres" -c "CREATE DATABASE \"$name\"" >/dev/null 2>&1; then
        ok "created database $name"
        created=$((created + 1))
      else
        warn "could not create $name (role lacks CREATEDB) — ask your DBA to run:"
        echo "      CREATE DATABASE \"$name\";"
      fi
    done
    [[ $created -gt 0 ]] || die "no database could be created; rerun this script afterwards"
  else
    die "cannot reach the server at ${LIBPQ_URL%/*} — is PostgreSQL running and are the credentials right?"
  fi
else
  ok "connected to $DB_NAME"
  psql "${LIBPQ_URL%/*}/postgres" -c "CREATE DATABASE \"$TEST_NAME\"" >/dev/null 2>&1 \
    && ok "created test database $TEST_NAME" \
    || ok "test database $TEST_NAME already present (or not creatable by this role)"
fi

# --------------------------------------------------------------------- migrate
say "2. Migrations"
BLOODLINK_DATABASE_URL="$APP_URL" python3 -m alembic upgrade head
BLOODLINK_DATABASE_URL="$APP_URL" python3 -m alembic check 2>/dev/null | tail -1 \
  || warn "alembic check reported drift — run it yourself to see the detail"
TABLES=$(psql "$LIBPQ_URL" -tAc "select count(*) from information_schema.tables where table_schema='public'")
ok "schema ready ($TABLES tables in $DB_NAME)"

# ----------------------------------------------------------------------- .env
if [[ "$WRITE_ENV" == "1" ]]; then
  say "3. Configuration ($ENV_FILE)"
  touch "$ENV_FILE"
  if grep -q '^BLOODLINK_DATABASE_URL=' "$ENV_FILE"; then
    # Portable in-place edit (GNU + BSD sed).
    tmp="$(mktemp)" && sed "s|^BLOODLINK_DATABASE_URL=.*|BLOODLINK_DATABASE_URL=$APP_URL|" "$ENV_FILE" > "$tmp" && mv "$tmp" "$ENV_FILE"
    ok "updated BLOODLINK_DATABASE_URL"
  else
    printf '\n# PostgreSQL (owner: D1)\nBLOODLINK_DATABASE_URL=%s\n' "$APP_URL" >> "$ENV_FILE"
    ok "added BLOODLINK_DATABASE_URL"
  fi
  if grep -q '^BLOODLINK_SECRET_KEY=' "$ENV_FILE"; then
    ok "BLOODLINK_SECRET_KEY already set"
  else
    secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    printf 'BLOODLINK_SECRET_KEY=%s\n' "$secret" >> "$ENV_FILE"
    ok "generated a BLOODLINK_SECRET_KEY"
  fi
  if grep -q '^BLOODLINK_SEED_ON_STARTUP=' "$ENV_FILE"; then
    ok "BLOODLINK_SEED_ON_STARTUP already set"
  else
    printf 'BLOODLINK_SEED_ON_STARTUP=true\n' >> "$ENV_FILE"
    ok "enabled demo seeding (set false for production)"
  fi
else
  say "3. Configuration"
  warn "--no-env: add this line to your .env yourself:"
  echo "      BLOODLINK_DATABASE_URL=$APP_URL"
fi

# ---------------------------------------------------------------- next steps
say "Next: run it (two terminals)"
cat <<EOF

  Terminal 1 — API on :8000
      make api                      # reads \$ENV_FILE
      # or explicitly:
      BLOODLINK_DATABASE_URL="$APP_URL" \\
        PYTHONPATH=apps/api:packages/config:packages/contracts:packages/validation \\
        python3 -m uvicorn bloodlink_api.main:app --reload --port 8000

  Terminal 2 — web client on :5173
      make web

  Then open http://localhost:5173 — demo accounts, password Bloodlink#2026:
      apollo.staff@bloodlink.dev   hospital   (review queue, request board)
      priya@bloodlink.dev          donor      (accept a matched request)
      redcross.staff@bloodlink.dev blood centre
      admin@bloodlink.dev          admin
  The first API start creates the tables and seeds the demo dataset.
  Guided tour: docs/demo-walkthrough.md

  Run the tests on this database:
      make test-postgres TEST_DATABASE_URL="${TEST_URL}"

  Reset the demo data (after a walkthrough consumes it):
      psql "$LIBPQ_URL" -c "TRUNCATE TABLE audit_logs, blood_request_events, blood_requests, conversations, donation_records, donor_outreach, donor_profiles, donor_responses, hospital_subscriptions, idempotency_records, messages, notification_deliveries, notifications, organization_memberships, organization_responses, organizations, patient_needs, push_subscriptions, refresh_tokens, users, verification_documents RESTART IDENTITY CASCADE;"
      # then restart the API (re-seeds) — or run: make seed
EOF
