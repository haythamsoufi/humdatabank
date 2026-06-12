"""
Load Backoffice/.env for test runner scripts (override=False).

Used by run_tests.bat / run_tests.ps1 so TEST_DATABASE_URL and other vars
from Backoffice/.env are available before pytest starts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import dotenv_values

BACKOFFICE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKOFFICE_DIR / ".env"


def vars_from_dotenv() -> dict[str, str]:
    """Return key/value pairs from Backoffice/.env (empty if file missing)."""
    if not ENV_FILE.is_file():
        return {}
    return {
        key: value
        for key, value in dotenv_values(ENV_FILE).items()
        if value is not None
    }


def vars_to_apply(existing: dict[str, str] | None = None) -> dict[str, str]:
    """Vars from .env that are not already set (matches config.py override=False)."""
    env = existing if existing is not None else os.environ
    return {
        key: value
        for key, value in vars_from_dotenv().items()
        if not (env.get(key) or "").strip()
    }


def _escape_cmd_value(value: str) -> str:
    return value.replace("%", "%%")


def write_cmd_file(path: Path, values: dict[str, str]) -> None:
    lines = [
        "@echo off",
        "REM Auto-generated from Backoffice/.env — do not edit",
    ]
    for key, value in sorted(values.items()):
        lines.append(f'set "{key}={_escape_cmd_value(value)}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load Backoffice/.env for test runners")
    parser.add_argument(
        "--emit-cmd",
        type=Path,
        help="Write cmd.exe SET commands for unset variables",
    )
    parser.add_argument(
        "--emit-json",
        action="store_true",
        help="Print unset variables as JSON on stdout",
    )
    args = parser.parse_args(argv)

    to_apply = vars_to_apply()

    if args.emit_cmd:
        write_cmd_file(args.emit_cmd, to_apply)
        return 0

    if args.emit_json:
        print(json.dumps(to_apply))
        return 0

    for key, value in to_apply.items():
        os.environ[key] = value
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
