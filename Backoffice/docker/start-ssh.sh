#!/bin/sh
# Opt-in OpenSSH daemon for Azure App Service custom-container SSH (break-glass access).
# Sourced by entrypoint.sh. Never aborts container start: any problem logs a warning and the
# app keeps booting without SSH.
#
#   ENABLE_SSH            true|1|yes|on to start sshd. Default: off (sshd is not started at all).
#   SSH_AUTH_MODE         platform (default) | key
#                           platform: root password auth enabled with the fixed value Azure's Portal
#                                     SSH / `az webapp ssh` authenticate with. Set at container start,
#                                     never stored in the image. Keys in SSH_AUTHORIZED_KEYS also work.
#                           key:      password auth disabled; only SSH_AUTHORIZED_KEYS can log in.
#                                     Use with `az webapp create-remote-connection` + `ssh -i`.
#   SSH_AUTHORIZED_KEYS   Public keys for root, separated by newlines or ';'. Options-prefixed keys
#                         (command=..., from=...) are rejected. Required when SSH_AUTH_MODE=key.
#   SSH_LISTEN_ADDRESS    Address for sshd to bind (default 0.0.0.0: the Kudu/SCM tunnel connects to the
#                         container's network address, not its loopback). Use 127.0.0.1 only for
#                         local `docker run -p` testing or if verified against the platform.
#   SSH_LEGACY_CRYPTO     true to additionally accept aes-cbc, hmac-sha1 and group14-sha1 for clients
#                         that cannot negotiate the modern set. Off by default.

_ssh_lower() { printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]'; }

_ssh_is_true() {
  case "$(_ssh_lower "${1:-}")" in
    1 | true | yes | on) return 0 ;;
  esac
  return 1
}

_ssh_install_authorized_keys() {
  _ssh_home="${SSH_ROOT_HOME:-/root}"
  mkdir -p "${_ssh_home}/.ssh"
  chmod 700 "${_ssh_home}/.ssh"
  _ssh_keys_file="${_ssh_home}/.ssh/authorized_keys"
  : > "$_ssh_keys_file"
  _ssh_key_count=0
  _ssh_key_list="$(printf '%s\n' "${SSH_AUTHORIZED_KEYS:-}" | tr ';' '\n' | tr -d '\r')"
  _ssh_old_ifs="$IFS"
  IFS='
'
  for _ssh_key in $_ssh_key_list; do
    _ssh_key="$(printf '%s' "$_ssh_key" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
    case "$_ssh_key" in
      ssh-ed25519\ * | ssh-rsa\ * | ecdsa-sha2-nistp*\ * | sk-ssh-ed25519@openssh.com\ * | sk-ecdsa-sha2-nistp256@openssh.com\ *)
        printf '%s\n' "$_ssh_key" >> "$_ssh_keys_file"
        _ssh_key_count=$((_ssh_key_count + 1))
        ;;
      "") ;;
      *) echo "WARN: SSH_AUTHORIZED_KEYS entry ignored (not a plain public key)." >&2 ;;
    esac
  done
  IFS="$_ssh_old_ifs"
  chmod 600 "$_ssh_keys_file"
}

start_app_service_ssh() {
  if ! _ssh_is_true "${ENABLE_SSH:-}"; then
    echo "SSH: disabled (set ENABLE_SSH=true to start the OpenSSH daemon on port 2222)."
    return 0
  fi

  _sshd_bin="${SSHD_BIN:-/usr/sbin/sshd}"
  _ssh_keygen_bin="${SSH_KEYGEN_BIN:-ssh-keygen}"
  _chpasswd_bin="${CHPASSWD_BIN:-chpasswd}"
  _sshd_config="${SSHD_CONFIG_FILE:-/etc/ssh/sshd_config}"

  if [ ! -x "$_sshd_bin" ]; then
    echo "WARN: SSH: ENABLE_SSH is set but $_sshd_bin is not installed; continuing without SSH." >&2
    return 0
  fi

  _ssh_mode="$(_ssh_lower "${SSH_AUTH_MODE:-platform}")"
  case "$_ssh_mode" in
    platform | key) ;;
    *)
      echo "WARN: SSH: unknown SSH_AUTH_MODE='${SSH_AUTH_MODE}' (use platform or key); continuing without SSH." >&2
      return 0
      ;;
  esac

  _ssh_listen="${SSH_LISTEN_ADDRESS:-0.0.0.0}"
  case "$_ssh_listen" in
    "" | *[!0-9a-fA-F:.]*)
      echo "WARN: SSH: invalid SSH_LISTEN_ADDRESS; continuing without SSH." >&2
      return 0
      ;;
  esac

  if [ -n "${SSH_AUTHORIZED_KEYS:-}" ]; then
    _ssh_install_authorized_keys
  fi

  if [ "$_ssh_mode" = "key" ] && [ "${_ssh_key_count:-0}" -eq 0 ]; then
    echo "WARN: SSH: SSH_AUTH_MODE=key needs at least one valid SSH_AUTHORIZED_KEYS entry; continuing without SSH." >&2
    return 0
  fi

  mkdir -p "${SSHD_RUN_DIR:-/run/sshd}"
  chmod 755 "${SSHD_RUN_DIR:-/run/sshd}"
  "$_ssh_keygen_bin" -A >/dev/null 2>&1 || {
    echo "WARN: SSH: could not generate host keys; continuing without SSH." >&2
    return 0
  }

  set -- -e -f "$_sshd_config" -o "ListenAddress=${_ssh_listen}"
  if [ "$_ssh_mode" = "key" ]; then
    set -- "$@" -o PasswordAuthentication=no -o PermitRootLogin=prohibit-password
  else
    # Azure's SSH proxy authenticates as root with this fixed, publicly documented value; it is set here
    # (not in the image) so it only exists in containers that explicitly opted in.
    printf 'root:%s\n' 'Docker!' | "$_chpasswd_bin" || {
      echo "WARN: SSH: could not set the platform SSH credential; continuing without SSH." >&2
      return 0
    }
  fi
  if _ssh_is_true "${SSH_LEGACY_CRYPTO:-}"; then
    echo "WARN: SSH: SSH_LEGACY_CRYPTO enabled (weaker CBC/SHA-1 algorithms accepted)." >&2
    set -- "$@" \
      -o "KexAlgorithms=curve25519-sha256,curve25519-sha256@libssh.org,ecdh-sha2-nistp256,ecdh-sha2-nistp384,ecdh-sha2-nistp521,diffie-hellman-group-exchange-sha256,diffie-hellman-group16-sha512,diffie-hellman-group18-sha512,diffie-hellman-group14-sha256,diffie-hellman-group14-sha1" \
      -o "Ciphers=chacha20-poly1305@openssh.com,aes256-gcm@openssh.com,aes128-gcm@openssh.com,aes256-ctr,aes192-ctr,aes128-ctr,aes256-cbc,aes128-cbc" \
      -o "MACs=hmac-sha2-256-etm@openssh.com,hmac-sha2-512-etm@openssh.com,hmac-sha2-256,hmac-sha2-512,hmac-sha1"
  fi

  if ! "$_sshd_bin" -t "$@" 2>/dev/null; then
    echo "WARN: SSH: sshd configuration test failed; continuing without SSH." >&2
    return 0
  fi

  echo "SSH: starting OpenSSH on ${_ssh_listen}:2222 (mode=${_ssh_mode}; logs go to the container log stream)."
  # env -i: the daemon does not need (and must not carry) the application's secrets in its environment.
  env -i PATH="$PATH" "$_sshd_bin" "$@" || echo "WARN: SSH: sshd failed to start; continuing without SSH." >&2
  return 0
}
