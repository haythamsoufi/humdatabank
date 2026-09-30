"""Static and behavioural checks for the container image's SSH hardening (no Docker required)."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

BACKOFFICE = Path(__file__).resolve().parents[2]
START_SSH = BACKOFFICE / "docker" / "start-ssh.sh"
PROFILE = BACKOFFICE / "docker" / "azure-ssh-profile.sh"
SSHD_CONFIG = BACKOFFICE / "sshd_config"
DOCKERFILE = BACKOFFICE / "Dockerfile"
ENTRYPOINT = BACKOFFICE / "entrypoint.sh"

pytestmark = pytest.mark.unit


def _sshd_directives() -> dict[str, str]:
    directives = {}
    for line in SSHD_CONFIG.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition(" ")
            directives[key.lower()] = value.strip()
    return directives


class TestStaticConfig:
    def test_dockerfile_does_not_bake_root_password_or_host_keys(self):
        text = DOCKERFILE.read_text()
        assert "chpasswd" not in text
        assert "Docker!" not in text
        assert "ssh-keygen" not in text

    def test_dockerfile_defaults_to_production(self):
        text = DOCKERFILE.read_text()
        assert "FLASK_CONFIG=production" in text
        assert "FLASK_CONFIG=development" not in text

    def test_entrypoint_starts_ssh_only_through_opt_in_helper(self):
        text = ENTRYPOINT.read_text()
        assert "/usr/sbin/sshd" not in text
        assert "start_app_service_ssh" in text

    def test_sshd_config_has_no_weak_algorithms(self):
        d = _sshd_directives()
        weak = re.compile(r"3des|cbc|sha1|arcfour|blowfish|group1-|group14-sha1")
        for name in ("ciphers", "macs", "kexalgorithms"):
            assert not weak.search(d[name]), f"{name} contains a weak algorithm"

    def test_sshd_config_disables_forwarding_and_limits_auth(self):
        d = _sshd_directives()
        for name in (
            "allowtcpforwarding",
            "allowstreamlocalforwarding",
            "gatewayports",
            "x11forwarding",
            "allowagentforwarding",
            "permittunnel",
            "permituserenvironment",
            "permitemptypasswords",
        ):
            assert d[name] == "no", name
        assert int(d["maxauthtries"]) <= 3
        assert int(d["logingracetime"]) <= 30
        assert d["allowusers"] == "root"
        assert d["port"] == "2222"

    def test_ssh_profile_exports_only_an_allowlist(self):
        text = PROFILE.read_text()
        assert "SSH_CONNECTION" in text
        for name in ("EMAIL_API_KEY", "OPENAI_API_KEY", "AZURE_STORAGE_CONNECTION_STRING"):
            assert name not in text.split("_SSH_DEFAULT_ENV_VARS=")[1].splitlines()[0]

    @pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
    def test_shellcheck_clean(self):
        result = subprocess.run(
            ["shellcheck", "-s", "sh", str(START_SSH), str(PROFILE), str(ENTRYPOINT)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout

    @pytest.mark.skipif(
        not (os.environ.get("SSHD_BIN") or shutil.which("sshd")),
        reason="sshd not installed (set SSHD_BIN to validate sshd_config)",
    )
    def test_sshd_config_validates_with_real_sshd(self, tmp_path):
        sshd = os.environ.get("SSHD_BIN") or shutil.which("sshd")
        for algo, bits in (("ed25519", None), ("rsa", "2048")):
            cmd = ["ssh-keygen", "-q", "-t", algo, "-N", "", "-f", str(tmp_path / f"ssh_host_{algo}_key")]
            if bits:
                cmd[4:4] = ["-b", bits]
            subprocess.run(cmd, check=True)
        cfg = tmp_path / "sshd_config"
        cfg.write_text(SSHD_CONFIG.read_text().replace("/etc/ssh/", f"{tmp_path}/"))
        result = subprocess.run([sshd, "-t", "-f", str(cfg)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


@pytest.fixture
def fake_bin(tmp_path):
    """Stub sshd/ssh-keygen/chpasswd that record how they were invoked."""
    log = tmp_path / "calls.log"
    passwd = tmp_path / "chpasswd.stdin"

    def _write(name, body):
        path = tmp_path / name
        path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    return {
        "log": log,
        "passwd": passwd,
        "home": tmp_path / "home",
        "env": {
            "SSHD_BIN": str(_write("sshd", f'echo "sshd $*" >> {log}\nexit 0\n')),
            "SSH_KEYGEN_BIN": str(_write("ssh-keygen", f'echo "keygen $*" >> {log}\nexit 0\n')),
            "CHPASSWD_BIN": str(_write("chpasswd", f"cat > {passwd}\n")),
            "SSHD_CONFIG_FILE": str(SSHD_CONFIG),
            "SSHD_RUN_DIR": str(tmp_path / "run-sshd"),
            "SSH_ROOT_HOME": str(tmp_path / "home"),
        },
    }


def _run_start(fake_bin, **env):
    full_env = {"PATH": os.environ["PATH"], **fake_bin["env"], **env}
    result = subprocess.run(
        ["sh", "-c", f". {START_SSH}; start_app_service_ssh"],
        env=full_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = fake_bin["log"].read_text() if fake_bin["log"].exists() else ""
    sshd_calls = [c for c in calls.splitlines() if c.startswith("sshd ") and " -t " not in c]
    return result, sshd_calls


ED25519 = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleExampleExampleExampleExampleExample ops@example"


class TestStartSsh:
    def test_disabled_by_default(self, fake_bin):
        result, sshd_calls = _run_start(fake_bin)
        assert sshd_calls == []
        assert not fake_bin["passwd"].exists()
        assert "disabled" in result.stdout

    @pytest.mark.parametrize("value", ["false", "0", "no", "", "maybe"])
    def test_falsey_values_do_not_start(self, fake_bin, value):
        _, sshd_calls = _run_start(fake_bin, ENABLE_SSH=value)
        assert sshd_calls == []

    def test_platform_mode_sets_credential_at_runtime_and_binds_all(self, fake_bin):
        result, sshd_calls = _run_start(fake_bin, ENABLE_SSH="true")
        assert len(sshd_calls) == 1
        assert "-e" in sshd_calls[0].split()
        assert "ListenAddress=0.0.0.0" in sshd_calls[0]
        assert "PasswordAuthentication=no" not in sshd_calls[0]
        assert fake_bin["passwd"].read_text().strip() == "root:Docker!"
        assert "Docker!" not in result.stdout + result.stderr
        assert "keygen -A" in fake_bin["log"].read_text()

    def test_listen_address_override(self, fake_bin):
        _, sshd_calls = _run_start(fake_bin, ENABLE_SSH="1", SSH_LISTEN_ADDRESS="127.0.0.1")
        assert "ListenAddress=127.0.0.1" in sshd_calls[0]

    def test_invalid_listen_address_is_rejected(self, fake_bin):
        result, sshd_calls = _run_start(fake_bin, ENABLE_SSH="true", SSH_LISTEN_ADDRESS="0.0.0.0;rm -rf /")
        assert sshd_calls == []
        assert "invalid SSH_LISTEN_ADDRESS" in result.stderr

    def test_key_mode_disables_password_and_never_sets_password(self, fake_bin):
        _, sshd_calls = _run_start(
            fake_bin, ENABLE_SSH="true", SSH_AUTH_MODE="key", SSH_AUTHORIZED_KEYS=ED25519
        )
        assert len(sshd_calls) == 1
        assert "PasswordAuthentication=no" in sshd_calls[0]
        assert "PermitRootLogin=prohibit-password" in sshd_calls[0]
        assert not fake_bin["passwd"].exists()
        keys = fake_bin["home"] / ".ssh" / "authorized_keys"
        assert keys.read_text().strip() == ED25519
        assert stat.S_IMODE(keys.stat().st_mode) == 0o600
        assert stat.S_IMODE(keys.parent.stat().st_mode) == 0o700

    def test_key_mode_without_keys_refuses_to_start(self, fake_bin):
        result, sshd_calls = _run_start(fake_bin, ENABLE_SSH="true", SSH_AUTH_MODE="key")
        assert sshd_calls == []
        assert "needs at least one valid" in result.stderr

    def test_authorized_keys_reject_option_prefixed_entries(self, fake_bin):
        hostile = 'command="/bin/sh",no-pty ' + ED25519
        _, sshd_calls = _run_start(
            fake_bin,
            ENABLE_SSH="true",
            SSH_AUTH_MODE="key",
            SSH_AUTHORIZED_KEYS=f"{hostile};{ED25519}",
        )
        assert len(sshd_calls) == 1
        keys = (fake_bin["home"] / ".ssh" / "authorized_keys").read_text().splitlines()
        assert keys == [ED25519]

    def test_unknown_auth_mode_does_not_start(self, fake_bin):
        result, sshd_calls = _run_start(fake_bin, ENABLE_SSH="true", SSH_AUTH_MODE="anything")
        assert sshd_calls == []
        assert "unknown SSH_AUTH_MODE" in result.stderr

    def test_legacy_crypto_is_opt_in(self, fake_bin):
        _, default_calls = _run_start(fake_bin, ENABLE_SSH="true")
        assert "hmac-sha1" not in default_calls[0]
        fake_bin["log"].unlink()
        result, legacy_calls = _run_start(fake_bin, ENABLE_SSH="true", SSH_LEGACY_CRYPTO="true")
        assert "MACs=" in legacy_calls[0] and "hmac-sha1" in legacy_calls[0]
        assert "SSH_LEGACY_CRYPTO enabled" in result.stderr

    def test_config_test_failure_keeps_app_booting(self, fake_bin, tmp_path):
        failing = tmp_path / "sshd-bad"
        failing.write_text('#!/bin/sh\ncase " $* " in *" -t "*) exit 1;; esac\necho started >> ' + str(fake_bin["log"]) + "\n")
        failing.chmod(0o755)
        fake_bin["env"]["SSHD_BIN"] = str(failing)
        result, _ = _run_start(fake_bin, ENABLE_SSH="true")
        assert "configuration test failed" in result.stderr
        assert "started" not in (fake_bin["log"].read_text() if fake_bin["log"].exists() else "")

    def test_missing_sshd_binary_keeps_app_booting(self, fake_bin):
        fake_bin["env"]["SSHD_BIN"] = "/nonexistent/sshd"
        result, sshd_calls = _run_start(fake_bin, ENABLE_SSH="true")
        assert sshd_calls == []
        assert "not installed" in result.stderr


class TestSshProfile:
    def _run(self, tmp_path, environ_bytes, **env):
        script = tmp_path / "profile.sh"
        text = PROFILE.read_text().replace("/proc/1/environ", str(tmp_path / "environ"))
        text = text.replace("[ -d /app ]", "[ -d /nonexistent-app ]")
        script.write_text(text)
        (tmp_path / "environ").write_bytes(environ_bytes)
        result = subprocess.run(
            ["sh", "-c", f'. {script}; printf "%s|%s|%s|%s" "${{DATABASE_URL:-}}" "${{EMAIL_API_KEY:-}}" "${{SECRET_KEY:-}}" "${{FLASK_CONFIG:-}}"'],
            env={"PATH": os.environ["PATH"], **env},
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    ENVIRON = b"DATABASE_URL=postgresql://x\0EMAIL_API_KEY=mail-secret\0SECRET_KEY=s3cr3t\0FLASK_CONFIG=production\0"

    def test_exports_only_allowlisted_vars_in_ssh_sessions(self, tmp_path):
        out = self._run(tmp_path, self.ENVIRON, SSH_CONNECTION="1.2.3.4 1 5.6.7.8 2222")
        assert out == "postgresql://x||s3cr3t|production"

    def test_no_export_outside_ssh_sessions(self, tmp_path):
        assert self._run(tmp_path, self.ENVIRON) == "|||"

    def test_allowlist_can_be_extended_explicitly(self, tmp_path):
        out = self._run(
            tmp_path,
            self.ENVIRON,
            SSH_CONNECTION="x",
            SSH_SHELL_ENV_VARS="DATABASE_URL EMAIL_API_KEY",
        )
        assert out == "postgresql://x|mail-secret||"

    def test_none_mode_exports_nothing(self, tmp_path):
        assert self._run(tmp_path, self.ENVIRON, SSH_CONNECTION="x", SSH_SHELL_ENV="none") == "|||"
