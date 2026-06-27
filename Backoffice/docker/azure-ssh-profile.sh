# Azure App Service SSH: /app, Flask CLI, and app env from the running container.
# SSH login shells do not inherit Azure App Settings; copy them from the web process.

_load_env_from_proc() {
  proc_path="$1"
  [ -r "$proc_path" ] || return 1
  while IFS= read -r line; do
    case "$line" in
      DATABASE_URL=*|SECRET_KEY=*|FLASK_CONFIG=*|FLASK_APP=*|REDIS_URL=*)
        export "$line" 2>/dev/null || true
        ;;
    esac
  done <<EOF
$(tr '\0' '\n' < "$proc_path")
EOF
}

if [ -z "${DATABASE_URL:-}" ]; then
  _load_env_from_proc /proc/1/environ
fi

if [ -z "${DATABASE_URL:-}" ]; then
  for _cmdline in /proc/[0-9]*/cmdline; do
    [ -r "$_cmdline" ] || continue
    if tr '\0' ' ' < "$_cmdline" 2>/dev/null | grep -q 'gunicorn.*run:app'; then
      _pid=$(echo "$_cmdline" | cut -d/ -f3)
      _load_env_from_proc "/proc/$_pid/environ"
      break
    fi
  done
fi

export FLASK_APP="${FLASK_APP:-run:app}"
if [ -z "${PYTHONPATH:-}" ]; then
  export PYTHONPATH=/app
elif ! echo "$PYTHONPATH" | grep -q '/app'; then
  export PYTHONPATH="/app:$PYTHONPATH"
fi
if [ -d /app ]; then
  cd /app || true
fi
