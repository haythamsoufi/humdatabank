#!/bin/sh
set -e

cd /app

echo "=========================================="
echo "Container entrypoint started"
echo "Time: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "FLASK_CONFIG: ${FLASK_CONFIG:-<not set>}"
echo "PORT: ${PORT:-5000}"
echo "SKIP_MIGRATIONS: ${SKIP_MIGRATIONS:-<not set>}"
echo "SEED_UPLOADS_ON_DEPLOY: ${SEED_UPLOADS_ON_DEPLOY:-<not set>}"
echo "DATABASE_URL: ${DATABASE_URL:+<set>}"
echo "=========================================="

# Seed persistent uploads from an archive on first boot when enabled.
# This checks SEED_UPLOADS_ON_DEPLOY and extracts /app/uploads.tgz into /data/uploads
# only if /data/uploads is empty.
SEED="${SEED_UPLOADS_ON_DEPLOY:-}"
if [ -n "$SEED" ] && [ -f "/app/uploads.tgz" ]; then
  if [ ! -d "/data/uploads" ] || [ -z "$(ls -A /data/uploads 2>/dev/null)" ]; then
    echo "Seeding /data/uploads from /app/uploads.tgz..."
    mkdir -p /data/uploads
    tar -xzf /app/uploads.tgz -C /data/uploads
  else
    echo "/data/uploads already contains files; skipping seed."
  fi
fi

# ---------------------------------------------------------------------------
# Persistent translations
# On Azure, mount an Azure Files share at /data/translations via Path
# Mappings (no extra env vars needed — the entrypoint auto-detects it).
# For docker-compose, a named volume is mounted at /app/translations.
# Override with TRANSLATIONS_PERSISTENT_PATH if you need a custom path.
# ---------------------------------------------------------------------------
TRANSLATIONS_PERSISTENT_PATH="${TRANSLATIONS_PERSISTENT_PATH:-}"

# Auto-detect: use /data/translations when it is an actual mount point
# (Azure Path Mapping) rather than just an empty image directory.
if [ -z "$TRANSLATIONS_PERSISTENT_PATH" ] && mountpoint -q /data/translations 2>/dev/null; then
  TRANSLATIONS_PERSISTENT_PATH="/data/translations"
  echo "Auto-detected Azure Files mount at /data/translations"
fi

if [ -n "$TRANSLATIONS_PERSISTENT_PATH" ]; then
  echo "=========================================="
  echo "Syncing translations to persistent volume"
  echo "TRANSLATIONS_PERSISTENT_PATH: $TRANSLATIONS_PERSISTENT_PATH"
  echo "=========================================="
  mkdir -p "$TRANSLATIONS_PERSISTENT_PATH"
  python scripts/sync_persistent_translations.py "$TRANSLATIONS_PERSISTENT_PATH"

  # Point /app/translations at the persistent path.  When the persistent
  # path is already mounted directly at /app/translations (e.g. Docker
  # named volume in docker-compose), skip the symlink — it's already there.
  APP_TRANSLATIONS="/app/translations"
  REAL_PERSISTENT="$(cd "$TRANSLATIONS_PERSISTENT_PATH" 2>/dev/null && pwd -P || echo "$TRANSLATIONS_PERSISTENT_PATH")"
  REAL_APP_TRANS="$(cd "$APP_TRANSLATIONS" 2>/dev/null && pwd -P || echo "$APP_TRANSLATIONS")"

  if [ "$REAL_PERSISTENT" != "$REAL_APP_TRANS" ]; then
    if [ -d "$APP_TRANSLATIONS" ] && [ ! -L "$APP_TRANSLATIONS" ]; then
      rm -rf "$APP_TRANSLATIONS"
    fi
    if [ ! -L "$APP_TRANSLATIONS" ]; then
      ln -s "$TRANSLATIONS_PERSISTENT_PATH" "$APP_TRANSLATIONS"
    fi
    echo "Symlinked $APP_TRANSLATIONS -> $TRANSLATIONS_PERSISTENT_PATH"
  else
    echo "Persistent volume already mounted at $APP_TRANSLATIONS"
  fi
else
  echo "TRANSLATIONS_PERSISTENT_PATH not set; using image-baked translations"
fi

if [ -z "${SKIP_MIGRATIONS:-}" ]; then
  echo "=========================================="
  echo "Preparing to run database migrations"
  echo "=========================================="

  # Ensure Flask CLI knows the app
  export FLASK_APP="run:app"

  # If DATABASE_URL is missing, migrations (and app boot) will fail anyway.
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is not set. Cannot run migrations." >&2
    exit 1
  fi

  # Wait for DB to accept connections (helps on cold starts / slot swaps).
  # Uses SQLAlchemy to attempt a simple connect.
  python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
timeout_s = int(os.environ.get("DB_WAIT_TIMEOUT", "120"))
# If DB_WAIT_INTERVAL is set, use it as a fixed interval; otherwise use exponential backoff.
fixed_interval_s = os.environ.get("DB_WAIT_INTERVAL")

start = time.time()
last_err = None
sleep_s = float(fixed_interval_s) if fixed_interval_s else 1.0
while time.time() - start < timeout_s:
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database connectivity check: OK", flush=True)
        sys.exit(0)
    except Exception as e:
        last_err = e
        print(f"Waiting for database... ({e})", file=sys.stderr, flush=True)
        time.sleep(sleep_s)
        if not fixed_interval_s:
            sleep_s = min(sleep_s * 1.7, 10.0)

print(f"ERROR: Database not reachable after {timeout_s}s: {last_err}", file=sys.stderr, flush=True)
sys.exit(1)
PY

  # Capture current alembic version (best-effort) so we can attempt rollback on failure.
  BEFORE_VER="$(python - <<'PY'
import os
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
try:
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        ver = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(ver or "")
except Exception as e:
    import sys
    print(f"# Could not get alembic version: {e}", file=sys.stderr)
    print("")
PY
)"

  echo "Running: python -m flask db upgrade"
  set +e
  python -m flask db upgrade 2>&1
  UPGRADE_EXIT=$?
  set -e

  if [ "$UPGRADE_EXIT" -ne 0 ]; then
    echo "==========================================" >&2
    echo "ERROR: Database migrations failed (exit=$UPGRADE_EXIT)" >&2
    echo "==========================================" >&2

    # IMPORTANT (production safety):
    # Do NOT auto-downgrade by default. Downgrades can be destructive and may drop data.
    # Only attempt rollback when explicitly enabled.
    ALLOW_ROLLBACK="$(echo "${MIGRATION_ALLOW_ROLLBACK:-}" | tr '[:upper:]' '[:lower:]')"
    if [ "$ALLOW_ROLLBACK" = "1" ] || [ "$ALLOW_ROLLBACK" = "true" ] || [ "$ALLOW_ROLLBACK" = "yes" ] || [ "$ALLOW_ROLLBACK" = "on" ]; then
      echo "MIGRATION_ALLOW_ROLLBACK is enabled; attempting best-effort rollback to previous revision: ${BEFORE_VER:-<unknown>}" >&2
      if [ -n "${BEFORE_VER:-}" ]; then
        set +e
        python -m flask db downgrade "${BEFORE_VER}" 2>&1
        DOWNGRADE_EXIT=$?
        set -e
        if [ "$DOWNGRADE_EXIT" -ne 0 ]; then
          echo "WARN: Rollback attempt failed (exit=$DOWNGRADE_EXIT). Manual intervention may be required." >&2
        else
          echo "✓ Rollback completed (downgraded to ${BEFORE_VER})" >&2
        fi
      else
        echo "WARN: Could not determine previous alembic revision; skipping rollback attempt." >&2
      fi
    else
      echo "Auto-rollback is disabled (set MIGRATION_ALLOW_ROLLBACK=true to enable)." >&2
      echo "Leaving database state as-is. Investigate migration failure and intervene manually." >&2
      echo "Tip: check current revision with: python -m flask db current" >&2
    fi

    exit "$UPGRADE_EXIT"
  fi

  echo "Running: python -m flask db current"
  python -m flask db current 2>&1 || true

  echo "=========================================="
  echo "RBAC permissions seeding (best-effort)"
  echo "=========================================="
  # Seed RBAC permissions/role-permissions if RBAC is enabled and permissions table is empty.
  # This prevents admin lockouts when migrations are applied but seeding is skipped.
  RBAC_SEED_ON_STARTUP="$(echo "${RBAC_SEED_ON_STARTUP:-false}" | tr '[:upper:]' '[:lower:]')"
  if [ "$RBAC_SEED_ON_STARTUP" != "false" ]; then
    python - <<'PY' 2>/dev/null && NEED_SEED=0 || NEED_SEED=1
import os
from sqlalchemy import create_engine, text

url = os.environ.get("DATABASE_URL")
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    # If RBAC tables don't exist yet, nothing to do.
    exists = conn.execute(text("""
        SELECT EXISTS (
          SELECT 1 FROM information_schema.tables
          WHERE table_name = 'rbac_permission'
        )
    """)).scalar()
    if not exists:
        raise SystemExit(0)
    count = conn.execute(text("SELECT COUNT(*) FROM rbac_permission")).scalar()
    if count and int(count) > 0:
        raise SystemExit(0)
raise SystemExit(1)
PY
    if [ "$NEED_SEED" -eq 1 ]; then
      echo "RBAC: rbac_permission is empty -> running: python -m flask rbac seed"
      python -m flask rbac seed 2>&1 || echo "WARN: RBAC seeding failed (continuing)"
    else
      echo "RBAC: permissions already seeded (skipping)"
    fi
  else
    echo "RBAC seeding skipped (RBAC_SEED_ON_STARTUP=false)"
  fi

  echo "=========================================="
  echo "✓ Database migrations completed"
  echo "=========================================="
else
  echo "Skipping migrations (SKIP_MIGRATIONS is set)"
fi

# If migrations are handled externally (e.g., by a separate db-init container),
# explicitly wait until DB is at Alembic head to avoid race conditions at startup.
WAIT_FOR_MIGRATIONS="${WAIT_FOR_MIGRATIONS:-true}"
if [ -n "${SKIP_MIGRATIONS:-}" ] && [ "$(echo "$WAIT_FOR_MIGRATIONS" | tr '[:upper:]' '[:lower:]')" != "false" ]; then
  echo "=========================================="
  echo "Waiting for external migrations to reach Alembic head"
  echo "WAIT_FOR_MIGRATIONS: ${WAIT_FOR_MIGRATIONS}"
  echo "MIGRATION_WAIT_TIMEOUT: ${MIGRATION_WAIT_TIMEOUT:-180}"
  echo "=========================================="
  python - <<'PY'
import os, sys, time
from sqlalchemy import create_engine, text
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

url = os.environ.get("DATABASE_URL")
timeout_s = int(os.environ.get("MIGRATION_WAIT_TIMEOUT", "180"))

alembic_ini = "/app/migrations/alembic.ini"
cfg = AlembicConfig(alembic_ini)
cfg.set_main_option("script_location", "/app/migrations")
cfg.set_main_option("sqlalchemy.url", url)
script = ScriptDirectory.from_config(cfg)
heads = set(script.get_heads() or [])

engine = create_engine(url, pool_pre_ping=True)
start = time.time()
last = None
while time.time() - start < timeout_s:
    try:
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        last = current
        if current in heads:
            print(f"✓ Alembic at head: {current}", flush=True)
            sys.exit(0)
        print(f"Waiting for migrations... current={current} heads={list(heads)}", flush=True)
    except Exception as e:
        print(f"Waiting for migrations... (no alembic_version yet): {e}", flush=True)
    time.sleep(2)

print(f"ERROR: Migrations not at head after {timeout_s}s (last={last}, heads={list(heads)})", file=sys.stderr, flush=True)
sys.exit(1)
PY
fi

if [ "$#" -gt 0 ]; then
  echo "=========================================="
  echo "Executing provided command (Azure Startup Command override)"
  echo "Command: $*"
  echo "=========================================="
  exec "$@"
fi

PORT="${PORT:-5000}"
echo "=========================================="
echo "Starting Gunicorn WSGI server (default)"
echo "Binding to: 0.0.0.0:${PORT}"
echo "=========================================="

# Use config file if it exists, otherwise use command-line args
# Logging is configured in gunicorn.conf.py to route INFO to stdout and WARNING/ERROR to stderr
if [ -f "config/gunicorn.conf.py" ]; then
    echo "Using config/gunicorn.conf.py for configuration"
    exec gunicorn --config config/gunicorn.conf.py run:app
else
    # Fallback to command-line configuration
    WORKERS=${GUNICORN_WORKERS:-1}
    THREADS=${GUNICORN_THREADS:-8}
    WORKER_CLASS=${GUNICORN_WORKER_CLASS:-gthread}
    TIMEOUT=${GUNICORN_TIMEOUT:-300}
    echo "Workers: ${WORKERS}, Threads: ${THREADS}, Worker Class: ${WORKER_CLASS}, Timeout: ${TIMEOUT}s"

    exec gunicorn --workers ${WORKERS} --threads ${THREADS} --worker-class ${WORKER_CLASS} \
      --max-requests 1000 --max-requests-jitter 100 \
      --timeout ${TIMEOUT} --keep-alive 10 \
      --bind "0.0.0.0:${PORT}" \
      --access-logfile - --error-logfile - --log-level info \
      --access-logformat '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"' \
      --capture-output \
      run:app
fi
