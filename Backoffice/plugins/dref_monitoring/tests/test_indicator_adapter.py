"""The temporary GO-title adapter links the same indicator and leaves the rest unmatched."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plugins.dref_monitoring.services.indicator_adapter import BankCatalog, canon

pytestmark = pytest.mark.unit


def _bank(bank_id, name, sector=None, translations=None):
    return SimpleNamespace(id=bank_id, name=name, sector=sector, name_translations=translations)


def test_shorthand_and_a_translation_link_the_bank_row():
    hygiene = _bank(1, "Number of people covered with hygiene promotion activities")
    french = _bank(
        2,
        "Number of people trained in first aid",
        translations={"fr": "Nombre de personnes formées aux premiers secours"},
    )
    shelter = _bank(5, "Number of people reached with shelter support.")
    catalog = BankCatalog([hygiene, french, shelter])
    assert canon("# of people covered") == canon("Number of people covered")
    assert canon("% of people covered") == canon("Percentage of people covered")
    assert catalog.adapt("# of people covered with hygiene promotion activities", None).id == 1
    assert catalog.adapt("Nombre de personnes formées aux premiers secours", None).id == 2
    assert catalog.adapt("# of people reached with shelter support (Shelter and settlement assistance)", None).id == 5


def test_a_short_extra_clause_still_links_and_a_count_does_not_become_a_percentage():
    shelter = _bank(5, "Number of people reached with shelter support.")
    percent = _bank(
        2,
        "Percentage of volunteers provided with equipment for protection, safety and support appropriate to the emergency.",
        sector={"primary": 9},
    )
    insured = _bank(3, "Number of volunteers covered by accident insurance.")
    catalog = BankCatalog([shelter, percent, insured])
    linked = catalog.adapt("# of people reached with shelter support in 2024", None)
    assert linked.id == 5
    assert (
        catalog.adapt(
            "# of volunteers provided with equipment for protection, safety and support appropriate to the emergency",
            9,
        )
        is None
    )
    assert (
        catalog.adapt(
            "% of volunteers provided with equipment for protection, safety and support appropriate to the emergency",
            9,
        ).id
        == 2
    )
    assert catalog.adapt("# of volunteers insured", None).id == 3
    assert catalog.adapt("Clinics opened this week", None) is None
