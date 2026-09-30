# Container SSH access (Azure App Service, break-glass)

> **Audience:** ops / on-call engineers who need a shell inside the production or staging container (for example to run `scripts/ops/*` maintenance scripts or `flask` CLI commands).

SSH into the container is **off by default**. It is a break-glass path, not a standing capability.

## Security posture

| Property | Behaviour | Where |
|---|---|---|
| sshd starts | Only when `ENABLE_SSH=true` (or `1/yes/on`). Otherwise nothing listens on 2222. | `docker/start-ssh.sh`, sourced by `entrypoint.sh` |
| Reachability | Port 2222 is **not** exposed publicly. It is only reachable through the Azure SCM/Kudu tunnel, which requires Azure RBAC on the Web App. | Azure platform |
| Root password | Not baked into the image. In `SSH_AUTH_MODE=platform` the fixed value Azure's Portal/`az webapp ssh` proxy authenticates with is applied at container start, only in containers that opted in. In `key` mode there is no password login at all. | `docker/start-ssh.sh` |
| Host keys | Generated at container start (never shared between images/instances). | `docker/start-ssh.sh` |
| Crypto | Modern KEX/ciphers/MACs only. `SSH_LEGACY_CRYPTO=true` re-adds CBC/SHA-1 (off by default). | `sshd_config` |
| Session limits | `AllowUsers root`, `MaxAuthTries 3`, `LoginGraceTime 30`, no TCP/agent/X11 forwarding, no user environment/rc files. | `sshd_config` |
| Audit trail | `LogLevel VERBOSE`, `sshd -e`: every auth attempt and session open is written to the container log stream (Log stream / Log Analytics `AppServiceConsoleLogs`). | `sshd_config`, `docker/start-ssh.sh` |
| Daemon environment | sshd runs under `env -i`; it does not carry application secrets. | `docker/start-ssh.sh` |
| Secrets in SSH sessions | Only an allowlist is copied into SSH login shells: `FLASK_CONFIG FLASK_APP DATABASE_URL SECRET_KEY MOBILE_JWT_SECRET AI_JWT_SECRET REDIS_URL`. Email, OpenAI, storage and DB-admin credentials are **not** exported. | `docker/azure-ssh-profile.sh` |

## Settings

Set as App Service **Application settings** (mark them deployment-slot specific if you do not want them to swap).

| Setting | Default | Meaning |
|---|---|---|
| `ENABLE_SSH` | unset (off) | Start sshd on 2222. Unset it again when finished. |
| `SSH_AUTH_MODE` | `platform` | `platform`: Portal / `az webapp ssh` work (root password auth enabled, keys also accepted). `key`: password auth disabled, only `SSH_AUTHORIZED_KEYS`. |
| `SSH_AUTHORIZED_KEYS` | unset | Public keys for `root`, separated by newlines or `;`. Plain keys only (`ssh-ed25519`, `ssh-rsa`, `ecdsa-*`, `sk-*`); entries with options are rejected. Required for `key` mode. |
| `SSH_LISTEN_ADDRESS` | `0.0.0.0` | Bind address. Leave alone on App Service. Use `127.0.0.1` only for local `docker run -p` tests. |
| `SSH_LEGACY_CRYPTO` | unset | `true` to also accept aes-cbc / hmac-sha1 / group14-sha1 (only if a client cannot negotiate the modern set). |
| `SSH_SHELL_ENV_VARS` | see above | Space-separated override of the variables copied into SSH shells. |
| `SSH_SHELL_ENV` | unset | `none` exports nothing into SSH shells. |

A misconfiguration never stops the app: `start-ssh.sh` logs a `WARN: SSH: ...` line and the container continues without sshd.

## Procedure A: key mode (preferred)

Use when you have the Azure CLI and an OpenSSH client.

1. Generate a short-lived key: `ssh-keygen -t ed25519 -f ~/.ssh/bo_breakglass -C "<you>-<date>"`.
2. Set `ENABLE_SSH=true`, `SSH_AUTH_MODE=key`, `SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/bo_breakglass.pub)"` on the Web App and let it restart.
3. Confirm in the log stream: `SSH: starting OpenSSH on 0.0.0.0:2222 (mode=key ...)`.
4. Open a tunnel: `az webapp create-remote-connection --name <app> --resource-group <rg> --port 2222` (prints a local port).
5. `ssh -i ~/.ssh/bo_breakglass -p <local-port> root@127.0.0.1`. The profile script `cd`s to `/app` and exports the allowlisted env.
6. When finished: remove `ENABLE_SSH`, `SSH_AUTH_MODE` and `SSH_AUTHORIZED_KEYS`, restart, and delete the key pair.

## Procedure B: platform mode (Portal / `az webapp ssh`)

1. Set `ENABLE_SSH=true` (leave `SSH_AUTH_MODE` unset) and restart.
2. Use Portal -> App Service -> **Development Tools -> SSH**, or `az webapp ssh --name <app> --resource-group <rg>`. The `azure-webapp/azure_webapp_run.ps1` helpers use the same tunnel.
3. When finished: remove `ENABLE_SSH` and restart.

The credential the Azure proxy uses is a documented, fixed platform value, so this mode is only as strong as the Azure RBAC that guards the SCM endpoint. That is why sshd is opt-in and time-boxed.

## Reviewing access

- Log stream / `AppServiceConsoleLogs`: search for `sshd`, `Accepted`, `Failed password`, `Invalid user`.
- Azure Activity Log: who changed the `ENABLE_SSH` application setting and when.
- Any period where `ENABLE_SSH` was set is a period where a shell was possible; review it after each use.

## Unverified assumptions (check on first use in staging)

- The Kudu/SCM tunnel client negotiates the modern-only crypto set. If Portal SSH or `az webapp ssh` fails with a key-exchange / cipher error, set `SSH_LEGACY_CRYPTO=true` temporarily and report the client version.
- The SCM container connects to the container's network address rather than loopback, hence the `0.0.0.0` default.
- `azure-webapp/azure_webapp_ssh_lib.ps1` currently forces `-o MACs=hmac-sha1,hmac-sha1-96` on the client. Until that is removed (it is outside the container image), the PowerShell helpers need `SSH_LEGACY_CRYPTO=true`.

## Local testing

```bash
docker build -t bo-ssh-test Backoffice
docker run --rm -e ENABLE_SSH=true -e SSH_AUTH_MODE=key -e SSH_LISTEN_ADDRESS=0.0.0.0 \
  -e SSH_AUTHORIZED_KEYS="$(cat ~/.ssh/id_ed25519.pub)" -p 127.0.0.1:2222:2222 bo-ssh-test
ssh -p 2222 root@127.0.0.1
```

Unit checks: `pytest tests/unit/test_container_hardening.py` (static assertions on the Dockerfile, `sshd_config`, entrypoint and profile script, plus `sshd -t` when an sshd binary is available).

## Upgrade notes

Older images baked `root:Docker!` and shared host keys into the layers and always started sshd. Once the hardened image is deployed, retire old image tags from the registry so those layers are no longer pullable.
