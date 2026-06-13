#!/bin/sh
set -eu

is_enabled() {
  value="$(printf '%s' "${1:-true}" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

run_with_retries() {
  label="$1"
  shift
  retries="${DB_STARTUP_RETRIES:-10}"
  delay="${DB_STARTUP_RETRY_DELAY:-3}"
  attempt=1

  while [ "$attempt" -le "$retries" ]; do
    echo "$label: attempt $attempt/$retries"
    if "$@"; then
      return 0
    fi

    if [ "$attempt" -eq "$retries" ]; then
      echo "$label: failed after $retries attempts" >&2
      return 1
    fi

    attempt=$((attempt + 1))
    sleep "$delay"
  done
}

if is_enabled "${RUN_DB_MIGRATIONS:-true}"; then
  run_with_retries "database migrations" alembic upgrade head
else
  echo "database migrations: skipped"
fi

if is_enabled "${RUN_SEED_DATA:-true}"; then
  run_with_retries "seed data" python -m seeds.bootstrap
else
  echo "seed data: skipped"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
