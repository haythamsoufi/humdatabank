"""Read/write pb_progress version-scoped state in the plugin_data table."""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

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
WORKBOOK_ARCHIVE_DIR = "source/archive"
MAX_WORKBOOK_HISTORY = 20


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
        "workbook_history": [],
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
    def _save_versions(cls, versions: dict[str, Any]) -> bool:
        return cls._store().set_nested(copy.deepcopy(versions), "versions")

    @classmethod
    def get_version_bucket(cls, version: str) -> dict[str, Any]:
        version = validate_version(version)
        bucket = copy.deepcopy(cls._versions().get(version, _default_version_bucket()))
        if not isinstance(bucket.get("status"), dict):
            bucket["status"] = _default_version_bucket()["status"]
        bucket.setdefault("data_source", "excel")
        bucket.setdefault("mapping_config", [])
        bucket.setdefault("translations_config", [])
        bucket.setdefault("section_order_config", [])
        bucket.setdefault("selected_years", [])
        bucket.setdefault("workbook_history", [])
        return bucket

    @classmethod
    def save_version_bucket(cls, version: str, bucket: dict[str, Any]) -> bool:
        version = validate_version(version)
        versions = cls._versions()
        versions[version] = copy.deepcopy(bucket)
        return cls._save_versions(versions)

    @classmethod
    def get_version_status(cls, version: str) -> dict[str, Any]:
        return copy.deepcopy(cls.get_version_bucket(version).get("status") or {})

    @classmethod
    def save_version_status(cls, version: str, status: dict[str, Any]) -> bool:
        bucket = cls.get_version_bucket(version)
        bucket["status"] = copy.deepcopy(status)
        return cls.save_version_bucket(version, bucket)

    @classmethod
    def get_data_source(cls, version: str) -> str:
        source = cls.get_version_bucket(version).get("data_source") or "excel"
        return source if source in {"excel", "system"} else "excel"

    @classmethod
    def set_data_source(cls, version: str, source: str) -> bool:
        if source not in {"excel", "system"}:
            raise ValueError(f"Invalid data source: {source!r}")
        bucket = cls.get_version_bucket(version)
        bucket["data_source"] = source
        return cls.save_version_bucket(version, bucket)

    @classmethod
    def get_mapping_config(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("mapping_config") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_mapping_config(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        bucket = cls.get_version_bucket(version)
        bucket["mapping_config"] = copy.deepcopy(rows)
        return cls.save_version_bucket(version, bucket)

    @classmethod
    def get_translations_config(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("translations_config") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_translations_config(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        bucket = cls.get_version_bucket(version)
        bucket["translations_config"] = copy.deepcopy(rows)
        return cls.save_version_bucket(version, bucket)

    @classmethod
    def get_section_order_config(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("section_order_config") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_section_order_config(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        bucket = cls.get_version_bucket(version)
        bucket["section_order_config"] = copy.deepcopy(rows)
        return cls.save_version_bucket(version, bucket)

    @classmethod
    def get_selected_years(cls, version: str) -> list[str]:
        years = cls.get_version_bucket(version).get("selected_years") or []
        if not isinstance(years, list):
            return []
        return [str(year).strip() for year in years if str(year).strip()]

    @classmethod
    def save_selected_years(cls, version: str, years: list[str]) -> bool:
        bucket = cls.get_version_bucket(version)
        bucket["selected_years"] = [str(year).strip() for year in years if str(year).strip()]
        return cls.save_version_bucket(version, bucket)

    @classmethod
    def get_workbook_history(cls, version: str) -> list[dict[str, Any]]:
        rows = cls.get_version_bucket(version).get("workbook_history") or []
        return copy.deepcopy(rows) if isinstance(rows, list) else []

    @classmethod
    def save_workbook_history(cls, version: str, rows: list[dict[str, Any]]) -> bool:
        bucket = cls.get_version_bucket(version)
        bucket["workbook_history"] = copy.deepcopy(rows)
        return cls.save_version_bucket(version, bucket)

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
