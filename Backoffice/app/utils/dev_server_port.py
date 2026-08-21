"""Dev-server port helpers for `python run.py`.

Windows lets two sockets bind the same TCP port when SO_REUSEADDR is set
(WSAEADDRINUSE is not raised). A second `python run.py` then shares :5000 with
the first and every request looks randomly slow. Probe without SO_REUSEADDR,
and refuse to start when something is already accepting connections — except
in the Werkzeug reloader child, which must re-bind after a restart.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess


def is_reloader_child() -> bool:
    """True inside the Werkzeug reloader worker (WERKZEUG_RUN_MAIN=true)."""
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def should_guard_existing_server() -> bool:
    """Refuse a second server only in the original process, not the reloader child."""
    return not is_reloader_child()


def connect_host(host: str) -> str:
    if host in ("0.0.0.0", "::", ""):
        return "127.0.0.1"
    return host


def port_has_listener(host: str, port: int, timeout: float = 0.4) -> bool:
    """True if something accepts TCP — an actual server, not TIME_WAIT."""
    target = connect_host(host)
    try:
        with socket.create_connection((target, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def pid_listening_on(port: int) -> int | None:
    """Best-effort PID of a process LISTENING on TCP `port` (Windows netstat)."""
    port = int(port)
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            errors="replace",
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    pattern = re.compile(rf":{port}\s+\S+\s+LISTENING\s+(\d+)\s*$")
    for line in out.splitlines():
        match = pattern.search(line)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def probe_bind(host: str, port: int) -> bool:
    """True if this process can bind `host:port`.

    Never sets SO_REUSEADDR: on Windows that reports an occupied port as free.
    SO_EXCLUSIVEADDRUSE makes the probe fail when another listener exists.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def find_available_port(host: str, start_port: int, max_tries: int = 20) -> int:
    """First port that is not serving HTTP and can be bound, else `start_port`."""
    start = int(start_port)
    for port in range(start, start + int(max_tries)):
        if port_has_listener(host, port):
            continue
        if probe_bind(host, port):
            return port
    return start


def occupied_server_message(host: str, port: int) -> str:
    pid = pid_listening_on(port)
    extra = f" (PID {pid})" if pid else ""
    stop = f"taskkill /F /PID {pid}" if pid else f"netstat -ano | findstr :{port}"
    return (
        f"Port {port} on {connect_host(host)} is already serving HTTP{extra}. "
        "Windows allows a second Flask to bind the same port, which makes "
        "requests slow and unpredictable. Stop the other `python run.py` "
        f"({stop}) or set FLASK_RUN_PORT to a free port."
    )
