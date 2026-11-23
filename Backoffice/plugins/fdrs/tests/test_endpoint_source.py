"""Source switch for the legacy FDRS public paths."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.models.plugin_data import PluginData
from plugins.fdrs.services.fdrs_endpoint_source import (
    PUBLIC_ENDPOINTS,
    SOURCE_DATABANK,
    SOURCE_ORIGINAL,
    apply_source_to_all_switchable,
    original_endpoint_paths,
    save_endpoint_sources,
    uses_original_api,
)


def _choices(**overrides: str) -> dict[str, str]:
    choices = {endpoint.id: SOURCE_DATABANK for endpoint in PUBLIC_ENDPOINTS if endpoint.switchable}
    choices.update(overrides)
    return choices


def test_every_switchable_endpoint_is_consulted_by_the_public_routes():
    source = Path(__file__).resolve().parents[1].joinpath("public_compat_routes.py").read_text(encoding="utf-8")
    missing = [
        endpoint.id
        for endpoint in PUBLIC_ENDPOINTS
        if endpoint.switchable and f'"{endpoint.id}"' not in source
    ]
    assert missing == []


def test_defaults_use_databank_and_locked_paths_stay_on_the_original_api(db_session):
    assert original_endpoint_paths() == []
    assert uses_original_api("data") is False
    assert uses_original_api("smarttran") is True
    assert uses_original_api("document_subscribe") is True
    assert uses_original_api("not-an-endpoint") is False


def test_save_forwards_only_the_chosen_paths_and_keeps_other_plugin_data(db_session):
    db_session.add(PluginData(plugin_id="fdrs", data={"keep": {"a": 1}, "public_endpoint_source": {"smarttran": "databank"}}))
    db_session.commit()

    assert uses_original_api("smarttran") is True
    assert save_endpoint_sources(_choices(data=SOURCE_ORIGINAL, csv_export=SOURCE_ORIGINAL)) is None

    db_session.expire_all()
    row = PluginData.query.filter_by(plugin_id="fdrs").one()
    assert row.data["keep"] == {"a": 1}
    assert row.data["public_endpoint_source"] == {"data": SOURCE_ORIGINAL, "csv_export": SOURCE_ORIGINAL}
    assert original_endpoint_paths() == ["/api/data", "/csv/export"]
    assert uses_original_api("documents") is False

    assert apply_source_to_all_switchable(SOURCE_ORIGINAL) is None
    switchable = [endpoint.path for endpoint in PUBLIC_ENDPOINTS if endpoint.switchable]
    assert original_endpoint_paths() == switchable
    assert uses_original_api("offices") is True

    assert apply_source_to_all_switchable(SOURCE_DATABANK) is None
    assert original_endpoint_paths() == []
    assert uses_original_api("tran") is True


def test_a_bad_choice_does_not_replace_a_saved_source(db_session):
    assert apply_source_to_all_switchable(SOURCE_ORIGINAL) is None
    choices = _choices()
    choices["data"] = "elsewhere"
    assert save_endpoint_sources(choices) == "Choose Databank or the original API for /api/data."
    assert "/api/documents" in original_endpoint_paths()

    incomplete = _choices()
    incomplete.pop("documents")
    assert save_endpoint_sources(incomplete) == "Choose a source for /api/documents."
    assert original_endpoint_paths()
    assert apply_source_to_all_switchable("legacy") == "Unknown source."


def test_a_hand_written_locked_override_cannot_move_that_path_onto_databank(db_session):
    row = PluginData(
        plugin_id="fdrs",
        data={"public_endpoint_source": {"offices": SOURCE_DATABANK, "kpi_value": SOURCE_ORIGINAL}},
    )
    db_session.add(row)
    db_session.commit()
    flag_modified(row, "data")
    db_session.commit()

    assert uses_original_api("offices") is True
    assert uses_original_api("kpi_value") is True
