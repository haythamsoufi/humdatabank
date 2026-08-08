"""Read/write pb_progress version-scoped state in the plugin_data table."""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.plugins.db_config import DbPluginConfig
from app.services.platform import storage_service
from plugins.pb_progress.versions import (
    DEFAULT_VERSION,
    LEGACY_EXCEL_REL_PATH,
    LEGACY_OUTPUT_PREFIX,
    LEGACY_STATUS_REL_PATH,
    REPORT_VERSIONS,
    VERSION_ORDER,
    validate_version,
    version_storage_prefix,
)

logger = logging.getLogger(__name__)

PLUGIN_ID = "pb_progress"
STORAGE_CATEGORY = "pb_progress"
STATUS_NAME = "status.json"
EXCEL_NAME = "source/SG_Report.xlsx"
SYSTEM_GENERATED_NAME = "source/system_generated.xlsx"

# How long a "running" status can go without a heartbeat before a new build
# claim is allowed to treat it as abandoned (worker crashed/killed mid-build)
# rather than genuinely in progress. Generous on purpose: Visuals-tool builds
# render several languages x formats and can legitimately go quiet for a
# while between build-log lines (heartbeats only refresh when a new log line
# arrives — see _consume_build_log_lines), so a short timeout would risk a
# second build starting while the first is still healthy.
BUILD_HEARTBEAT_STALE_SECONDS = 20 * 60


def _running_status_age_seconds(status: dict[str, Any]) -> float | None:
    """Seconds since a 'running' status last proved it's alive, or None if unknown."""
    timestamp = status.get("heartbeat") or status.get("started_at")
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(timestamp))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds()


def _is_running_status_stale(status: dict[str, Any]) -> bool:
    """Whether a 'running' status is old enough to be treated as abandoned.

    Fails closed: a missing or unparseable timestamp counts as NOT stale (still
    blocks new claims) so a build that just started — before its first
    heartbeat write — is never mistaken for an abandoned one.
    """
    age = _running_status_age_seconds(status)
    return age is not None and age >= BUILD_HEARTBEAT_STALE_SECONDS


def _default_version_bucket() -> dict[str, Any]:
    return {
        "status": {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "build_stage": None,
            "output_names": [],
            "excel": None,
            "outputs": [],
        },
        "data_source": "excel",
        "mapping_config": [],
        "translations_config": [],
        "section_order_config": [],
        "selected_years": [],
    }


def _default_data() -> dict[str, Any]:
    return {
        "versions": {version_id: _default_version_bucket() for version_id in VERSION_ORDER},
        "legacy_migrated": False,
    }


class PBProgressDataStore:
    """Thin wrapper around DbPluginConfig for pb_progress version buckets."""

    _config: DbPluginConfig | None = None

    @classmethod
    def _store(cls) -> DbPluginConfig:
        if cls._config is None:
            cls._config = DbPluginConfig(PLUGIN_ID, _default_data())
        return cls._config

    @classmethod
    def _versions(cls) -> dict[str, Any]:
        data = cls._store()._read_config()
        versions = data.get("versions")
        if not isinstance(versions, dict):
            versions = {}
            data["versions"] = versions
        for version_id in VERSION_ORDER:
            bucket = versions.get(version_id)
            if not isinstance(bucket, dict):
                versions[version_id] = _default_version_bucket()
        return versions

    @classmethod
    def _apply_bucket_defaults(cls, bucket: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(bucket.get("status"), dict):
            bucket["status"] = _default_version_bucket()["status"]
        bucket.setdefault("data_source", "excel")
        bucket.setdefault("mapping_config", [])
        bucket.setdefault("translations_config", [])
        bucket.setdefault("section_order_config", [])
        bucket.setdefault("selected_years", [])
        return bucket

    @classmethod
    def get_version_bucket(cls, version: str) -> dict[str, Any]:
        version = validate_version(version)
        bucket = copy.deepcopy(cls._versions().get(version, _default_version_bucket()))
        return cls._apply_bucket_defaults(bucket)

    @classmethod
    def _atomic_update_bucket(
        cls,
        version: str,
        mutate: Callable[[dict[str, Any]], bool | None],
    ) -> bool:
        """Read-modify-write exactly one version bucket under a single row lock.

        Every save_* method below used to do an *unlocked* get_version_bucket()
        read, mutate one field of the returned dict in Python, then write the
        whole bucket back — so two concurrent requests (different browser tabs,
        different admins, or a config save racing a build-completion status
        write) that each touched a different field of the same version's bucket
        (or different versions in the same shared plugin_data row) could silently
        clobber each other: whichever commit landed last would overwrite the
        other's change with its own now-stale snapshot of everything else.

        Taking the row lock (SELECT ... FOR UPDATE) *before* reading serializes
        concurrent writers — each one blocks until the previous commit is
        visible — so `mutate` always edits the latest state. `mutate` edits the
        live bucket dict in place; return `False` from `mutate` to abort without
        committing (e.g. a precondition failed), anything else commits normally.

        Mirrors DbPluginConfig._save_config's "no app context -> log + return
        False" contract (rather than letting db.session raise) since this
        bypasses that class's own read/write helpers to get the row lock. A few
        call sites (e.g. import_config_from_excel) invoke save_* methods from
        plain unit tests with no Flask app context pushed, and previously relied
        on this method silently no-oping.
        """
        from flask import has_app_context

        version = validate_version(version)
        if not has_app_context():
            logger.warning(
                "Cannot persist pb_progress bucket for version %s outside application context",
                version,
            )
            return False

        from app.extensions import db

        store = cls._store()
        try:
            row = store._get_or_create_row(for_update=True)
            raw = row.data if isinstance(row.data, dict) else {}
            data = store._merge_with_defaults(raw)
            versions = data.setdefault("versions", {})
            bucket = versions.get(version)
            if not isinstance(bucket, dict):
                bucket = _default_version_bucket()
            bucket = cls._apply_bucket_defaults(bucket)

            if mutate(bucket) is False:
                db.session.rollback()
                return False

            versions[version] = bucket
            data["versions"] = versions
            row.data = data
            store.config = copy.deepcopy(data)
            db.session.commit()
            return True
        except Exception as exc:
            db.session.rollback()
            logger.error("Failed to save pb_progress bucket for version %s: %s", version, exc, exc_info=True)
            return False

    @classmethod
    def save_version_bucket(cls, version: str, bucket: dict[str, Any]) -> bool:
        incoming = copy.deepcopy(bucket)

        def mutate(current: dict[str, Any]) -> None:
            current.clear()
            current.update(incoming)

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def get_version_status(cls, version: str) -> dict[str, Any]:
        return copy.deepcopy(cls.get_version_bucket(version).get("status") or {})

    @classmethod
    def save_version_status(cls, version: str, status: dict[str, Any]) -> bool:
        incoming = copy.deepcopy(status)

        def mutate(bucket: dict[str, Any]) -> None:
            bucket["status"] = incoming

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def get_data_source(cls, version: str) -> str:
        source = cls.get_version_bucket(version).get("data_source") or "excel"
        return source if source in {"excel", "system"} else "excel"

    @classmethod
    def set_data_source(cls, version: str, source: str) -> bool:
        if source not in {"excel", "system"}:
            raise ValueError(f"Invalid data source: {source!r}")

        def mutate(bucket: dict[str, Any]) -> None:
            bucket["data_source"] = source

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def get_mapping_config(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("mapping_config") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_mapping_config(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        incoming = copy.deepcopy(rows)

        def mutate(bucket: dict[str, Any]) -> None:
            bucket["mapping_config"] = incoming

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def get_translations_config(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("translations_config") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_translations_config(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        incoming = copy.deepcopy(rows)

        def mutate(bucket: dict[str, Any]) -> None:
            bucket["translations_config"] = incoming

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def get_section_order_config(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("section_order_config") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_section_order_config(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        incoming = copy.deepcopy(rows)

        def mutate(bucket: dict[str, Any]) -> None:
            bucket["section_order_config"] = incoming

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def get_selected_years(cls, version: str) -> list[str]:
        years = cls.get_version_bucket(version).get("selected_years") or []
        if not isinstance(years, list):
            return []
        return [str(year).strip() for year in years if str(year).strip()]

    @classmethod
    def save_selected_years(cls, version: str, years: list[str]) -> bool:
        cleaned = [str(year).strip() for year in years if str(year).strip()]

        def mutate(bucket: dict[str, Any]) -> None:
            bucket["selected_years"] = cleaned

        return cls._atomic_update_bucket(version, mutate)

    @classmethod
    def try_set_version_status_if_not_running(cls, version: str, status: dict[str, Any]) -> bool:
        """Atomically claim the *plugin-wide* build slot for `version`.

        Only one Visuals-tool build may run at a time across the whole
        deployment, not just within one worker process. Each build spawns
        its own subprocess pool and is heavy enough that two running at once
        can starve a small box — but ``start_generation``'s in-process guard
        (``cls._build_thread.is_alive()``) only sees builds *this* worker
        started. Two different Gunicorn workers could each pass that guard
        for two *different* versions and start building concurrently, since
        neither worker's in-memory state knows about the other's build.

        This locks the single shared plugin_data row (the same lock every
        other atomic write in this class uses) and checks the status of
        *every* version, not just ``version`` — so it serializes the claim
        across every worker process talking to the same database, for any
        version. A "running" status blocks the claim unless its heartbeat
        has gone stale (see ``BUILD_HEARTBEAT_STALE_SECONDS``), which means
        the worker that owned it crashed or was killed mid-build; in that
        case the slot is reclaimed instead of staying wedged forever.

        Same no-app-context contract as _atomic_update_bucket: log + return
        False instead of letting db.session raise.
        """
        from flask import has_app_context

        version = validate_version(version)
        if not has_app_context():
            logger.warning(
                "Cannot claim pb_progress build slot for version %s outside application context",
                version,
            )
            return False

        from app.extensions import db

        incoming = copy.deepcopy(status)
        store = cls._store()
        try:
            row = store._get_or_create_row(for_update=True)
            raw = row.data if isinstance(row.data, dict) else {}
            data = store._merge_with_defaults(raw)
            versions = data.setdefault("versions", {})

            for candidate_id in VERSION_ORDER:
                candidate_bucket = versions.get(candidate_id)
                if not isinstance(candidate_bucket, dict):
                    continue
                candidate_status = candidate_bucket.get("status")
                if not isinstance(candidate_status, dict):
                    continue
                if candidate_status.get("status") != "running":
                    continue
                if not _is_running_status_stale(candidate_status):
                    db.session.rollback()
                    return False

            bucket = versions.get(version)
            if not isinstance(bucket, dict):
                bucket = _default_version_bucket()
            bucket = cls._apply_bucket_defaults(bucket)
            bucket["status"] = incoming
            versions[version] = bucket
            data["versions"] = versions
            row.data = data
            store.config = copy.deepcopy(data)
            db.session.commit()
            return True
        except Exception as exc:
            db.session.rollback()
            logger.error(
                "Failed to claim pb_progress build slot for version %s: %s", version, exc, exc_info=True
            )
            return False

    @classmethod
    def _version_rel(cls, version: str, name: str) -> str:
        return f"{version_storage_prefix(version)}{name}"

    @classmethod
    def _status_rel(cls, version: str) -> str:
        return cls._version_rel(version, STATUS_NAME)

    @classmethod
    def _load_status_json(cls, rel_path: str) -> dict[str, Any] | None:
        if not storage_service.exists(STORAGE_CATEGORY, rel_path):
            return None
        try:
            raw = storage_service.download(STORAGE_CATEGORY, rel_path)
            payload = json.loads(raw.decode("utf-8"))
            return payload if isinstance(payload, dict) else None
        except Exception as exc:
            logger.warning("Failed to load legacy pb_progress status %s: %s", rel_path, exc)
            return None

    @classmethod
    def migrate_legacy_storage_if_needed(cls) -> None:
        store = cls._store()
        data = store._read_config()
        if data.get("legacy_migrated"):
            return

        versions = cls._versions()
        changed = False

        target = DEFAULT_VERSION
        if not versions.get(target, {}).get("status", {}).get("finished_at"):
            legacy_status = cls._load_status_json(LEGACY_STATUS_REL_PATH)
            if legacy_status:
                bucket = versions.setdefault(target, _default_version_bucket())
                bucket["status"] = legacy_status
                changed = True

        for version_id in VERSION_ORDER:
            rel = cls._status_rel(version_id)
            persisted = cls._load_status_json(rel)
            if persisted:
                bucket = versions.setdefault(version_id, _default_version_bucket())
                existing = bucket.get("status") or {}
                if not existing.get("finished_at") and existing.get("status", "idle") == "idle":
                    bucket["status"] = persisted
                    changed = True

        data["legacy_migrated"] = True
        data["versions"] = versions
        store._save_config(data)
        if changed:
            logger.info("Migrated legacy pb_progress status.json files into plugin_data")
