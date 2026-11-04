"""Decision and rule configuration. Hardcoded in ``config.py`` for now; nothing is read from the database."""

from __future__ import annotations

from typing import Any

from plugins.ifrc.decisions import config


def load_decisions() -> dict[str, dict[str, Any]]:
    return config.default_decisions()


def load_rules() -> dict[str, dict[str, Any]]:
    return config.default_rules()
