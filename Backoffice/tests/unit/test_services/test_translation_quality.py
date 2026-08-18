"""Tests for catalog, glossary forcing, cache keys, and mining extractors."""

from app.services.translation.catalog_service import classify_catalog_msgids, msgid_hash
from app.services.translation.glossary_forcing import (
    enforce_glossary_terms,
    protect_glossary_terms,
    restore_glossary_tokens,
)
from app.services.translation.glossary_llm import (
    classify_against_glossary,
    dedupe_source_terms,
    ground_pairs,
    term_is_attested,
    usable_glossary_term,
)
from app.services.translation.glossary_mining import _extract_acronyms
from app.services.translation.gold_eval import chr_f, gold_set_ready, simple_term_hit_rate
from app.services.translation.result_cache import source_hash


def test_msgid_hash_matches_audit_style():
    assert len(msgid_hash("Focal Point")) == 16
    assert msgid_hash("Focal Point") == msgid_hash("Focal Point")
    assert msgid_hash("a") != msgid_hash("b")


def test_glossary_forces_focal_point_french():
    terms = [("Focal Point", "point focal")]
    protected, token_map, hits = protect_glossary_terms(
        "Assign a Focal Point to the country", "fr", terms=terms
    )
    assert hits >= 1
    assert "Focal Point" not in protected
    restored = restore_glossary_tokens(protected, token_map)
    assert "point focal" in restored.lower()
    assert "point central" not in restored.lower()


def test_enforce_glossary_keeps_arabic_word_order():
    terms = [
        ("Focal Point", "نقطة اتصال"),
        ("Focal Points", "نقاط اتصال"),
    ]
    unofficial = {
        "Focal Point": "نقطة محورية",
        "Focal Points": "النقاط المحورية",
    }

    out = enforce_glossary_terms(
        "%(org)s focal point names",
        "%(org)s أسماء النقاط المحورية",
        "ar",
        unofficial.get,
        terms=terms,
    )
    assert out == "%(org)s أسماء نقاط الاتصال"
    assert "نقطة اتصال أسماء" not in out


def test_enforce_glossary_swaps_unofficial_french():
    out = enforce_glossary_terms(
        "Assign a Focal Point to the country",
        "Assigner un point central au pays",
        "fr",
        lambda term: "point central" if term == "Focal Point" else None,
        terms=[("Focal Point", "point focal")],
    )
    assert "point focal" in out.lower()
    assert "point central" not in out.lower()


def test_enforce_glossary_needs_unofficial_from_engine_not_code_aliases():
    out = enforce_glossary_terms(
        "%(org)s focal point names",
        "%(org)s أسماء النقاط المحورية",
        "ar",
        lambda term: "نقطة اتصال" if term == "Focal Point" else "نقاط اتصال",
        terms=[("Focal Point", "نقطة اتصال"), ("Focal Points", "نقاط اتصال")],
    )
    assert out == "%(org)s أسماء النقاط المحورية"


def test_enforce_glossary_leaves_unrelated_text():
    out = enforce_glossary_terms(
        "Hello world",
        "Bonjour le monde",
        "fr",
        lambda _term: None,
        terms=[("Focal Point", "point focal")],
    )
    assert out == "Bonjour le monde"


def test_glossary_does_not_touch_unrelated_text():
    protected, token_map, hits = protect_glossary_terms(
        "Hello world", "fr", terms=[("Focal Point", "point focal")]
    )
    assert hits == 0
    assert protected == "Hello world"
    assert token_map == {}


def test_acronym_extractor_joins_on_cva():
    hits = _extract_acronyms("Cash and Voucher Assistance (CVA) is used widely.")
    assert any(h["acronym"] == "CVA" for h in hits)
    assert any("Cash and Voucher Assistance" in h["expansion"] for h in hits)


def test_acronym_extractor_rejects_page_noise_and_stopwords():
    assert _extract_acronyms("[Page 2] International Federation") == []
    assert _extract_acronyms("Something (THE) is not an acronym.") == []
    assert _extract_acronyms("Change\nNisswen\nEngedal (IFRC)") == []


def test_llm_term_helpers_reject_noise():
    assert usable_glossary_term("[Page 2] Red Cross") is None
    assert usable_glossary_term("National Societies") == "National Societies"
    assert term_is_attested("Sociétés nationales", "Grâce à nos Sociétés nationales, le réseau agit.")
    assert not term_is_attested("sociétés inventées", "Grâce à nos Sociétés nationales, le réseau agit.")


def test_llm_ground_pairs_keeps_attested_and_drops_hallucinations():
    excerpts = {
        "National Societies": "Grâce à nos Sociétés nationales, le réseau agit.",
        "Strategy 2030": "[page 5] La Stratégie 2030 porte sur les changements.",
    }
    kept = ground_pairs(
        [
            {
                "source_term": "National Societies",
                "target_term": "Sociétés nationales",
                "target_evidence": "nos Sociétés nationales",
                "confidence": 0.8,
            },
            {
                "source_term": "Strategy 2030",
                "target_term": "une traduction inventée",
                "target_evidence": "inventée",
                "confidence": 0.9,
            },
            {
                "source_term": "Red Cross",
                "target_term": "x" * 300,
                "target_evidence": "x" * 300,
            },
        ],
        excerpts,
        target_lang="fr",
    )
    assert [(p["source_term"], p["target_term"]) for p in kept] == [
        ("National Societies", "Sociétés nationales")
    ]


def test_classify_against_glossary_same_conflict_and_new():
    glossary = {("national societies", "fr"): "Sociétés nationales"}
    assert classify_against_glossary("National Societies", "Sociétés nationales", "fr", glossary) == "same"
    assert classify_against_glossary("National Societies", "sociétés nationales", "fr", glossary) == "same"
    assert classify_against_glossary("National Societies", "sociétés nationales de la Croix-Rouge", "fr", glossary) == "conflict"
    assert classify_against_glossary("Cash and Voucher Assistance", "assistance en espèces", "fr", glossary) == "new"


def test_llm_dedupe_source_terms():
    rows = dedupe_source_terms(
        [
            {"term": "National Societies", "evidence": "Our 192 National Societies work locally."},
            {"term": "national societies", "evidence": "National Societies are members."},
            {"term": "[Page 1] Strategy", "evidence": "Strategy"},
        ]
    )
    assert [r["term"] for r in rows] == ["National Societies"]


def test_source_hash_stable():
    assert source_hash("abc") == source_hash("abc")
    assert source_hash("abc") != source_hash("abcd")


def test_result_cache_engine_is_generation_versioned():
    from app.services.translation.result_cache import RESULT_CACHE_GENERATION, _engine_key

    assert _engine_key("nllb") == f"nllb:{RESULT_CACHE_GENERATION}"
    assert _engine_key("nllb") != "nllb"


def test_term_hit_rate():
    assert simple_term_hit_rate("le point focal", "le point focal national", ["point focal"]) == 1.0
    assert simple_term_hit_rate("le point central", "le point focal national", ["point focal"]) == 0.0


def test_gold_set_not_ready_when_empty():
    assert gold_set_ready({"segments": []}) is False


def test_gold_fixture_exists_and_is_not_ready():
    from pathlib import Path

    from app.services.translation.gold_eval import DEFAULT_FIXTURE, load_gold_set

    assert DEFAULT_FIXTURE.exists() or (
        Path(__file__).resolve().parents[2] / "fixtures" / "translation_gold_set.json"
    ).exists()
    payload = load_gold_set()
    assert payload.get("segments")
    assert gold_set_ready(payload) is False


def test_website_french_locale_is_valid_json():
    from app.services.translation.catalog_hygiene import website_locale_status

    status = website_locale_status()
    assert status.get("fr") == "ok"


def test_dead_locales_are_pruned():
    from app.services.translation.catalog_hygiene import dead_locale_paths

    assert dead_locale_paths() == []


def test_filelock_status_reports_available_in_ci_and_dev():
    from app.services.translation.catalog_hygiene import filelock_status

    status = filelock_status()
    assert status["available"] is True


def test_hygiene_report_includes_filelock_protection():
    from app.services.translation.catalog_hygiene import hygiene_report

    report = hygiene_report()
    assert "filelock_protection" in report
    assert report["filelock_protection"]["available"] is True


def test_obsolete_duplicate_of_live_pot_string_is_not_removed():
    active, removed = classify_catalog_msgids(
        ["Focal Point", "Save"],
        ["Focal Point", "Save", "Focal Point"],
    )
    assert active == {"Focal Point", "Save"}
    assert removed == set()


def test_msgid_missing_from_pot_is_removed():
    active, removed = classify_catalog_msgids(["Save"], ["Save", "Old label"])
    assert "Save" in active
    assert removed == {"Old label"}


def test_chr_f_prefers_closer_hypothesis():
    assert chr_f("le point focal", "le point focal") > chr_f("le point central", "le point focal")


def test_glossary_term_repo_create_list_update_and_deactivate(db_session):
    from app.services.translation.glossary_terms import (
        GlossaryTermError,
        list_glossary_terms,
        update_glossary_term,
        upsert_glossary_term,
    )

    created = upsert_glossary_term(
        source_term="Focal Point",
        target_term="نقطة اتصال",
        target_lang="ar",
        tier="must",
    )
    assert created["source_term"] == "Focal Point"
    assert created["target_term"] == "نقطة اتصال"
    assert created["is_active"] is True

    listed = list_glossary_terms(target_lang="ar", search="Focal")
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]

    updated = update_glossary_term(created["id"], target_term="نقاط اتصال", is_active=False)
    assert updated["target_term"] == "نقاط اتصال"
    assert updated["is_active"] is False
    assert list_glossary_terms(target_lang="ar")["total"] == 0
    assert list_glossary_terms(target_lang="ar", include_inactive=True)["total"] == 1

    try:
        upsert_glossary_term(source_term="", target_term="x", target_lang="fr")
        assert False, "expected invalid source"
    except GlossaryTermError as exc:
        assert str(exc) == "invalid_source"
