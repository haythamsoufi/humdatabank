# Azure App Service SSH: /app, Flask CLI and the minimum app env from the running container.
# SSH login shells do not inherit Azure App Settings, so a fixed allowlist is copied from the web
# process into SSH sessions only (never into other shells). Least privilege: everything not listed
# (email/OpenAI/storage keys, DB admin creds, ...) is deliberately NOT exported.
#
#   SSH_SHELL_ENV_VARS  space-separated override of the allowlist (e.g. add EMAIL_API_KEY for a
#                       one-off mail script). Names must be [A-Z_][A-Z0-9_]*.
#   SSH_SHELL_ENV=none  export nothing (bring your own env).

_SSH_DEFAULT_ENV_VARS="FLASK_CONFIG FLASK_APP DATABASE_URL SECRET_KEY MOBILE_JWT_SECRET AI_JWT_SECRET REDIS_URL"

_ssh_env_allowed() {
  for _allowed in ${SSH_SHELL_ENV_VARS:-$_SSH_DEFAULT_ENV_VARS}; do
    [ "$_allowed" = "$1" ] && return 0
  done
  return 1
}

_load_env_from_proc() {
  proc_path="$1"
  [ -r "$proc_path" ] || return 1
  while IFS= read -r line; do
    case "$line" in
      [A-Z_]*=*)
        _name="${line%%=*}"
        case "$_name" in
          *[!A-Z0-9_]*) continue ;;
        esac
        if _ssh_env_allowed "$_name"; then
          # shellcheck disable=SC2163  # "NAME=value" form is intentional
          export "$line" 2>/dev/null || true
        fi
        ;;
    esac
  done <<EOF
$(tr '\0' '\n' < "$proc_path")
EOF
}

if [ -n "${SSH_CONNECTION:-}" ] && [ "${SSH_SHELL_ENV:-}" != "none" ]; then
  _load_env_from_proc /proc/1/environ

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
