"""Export-language helpers and RTL/narrative translation wiring."""

from __future__ import annotations

import pytest

from plugins.upr_visuals.i18n import (
    can_machine_translate,
    current_export_language,
    get_visuals_progress,
    is_rtl,
    localize_export,
    localized_country_header,
    localized_country_name,
    localized_ns_display_name,
    parse_export_language,
    parse_progress_id,
    rtl_css,
    rtl_document_attrs,
    start_visuals_progress,
    t,
    t_batch,
    translate_styled_blocks,
    update_visuals_progress,
    uses_arabic_font,
)


@pytest.mark.unit
def test_parse_export_language_known_and_fallback():
    assert parse_export_language("fr") == "fr"
    assert parse_export_language("AR-EG") == "ar"
    assert parse_export_language("nope") == "en"
    with pytest.raises(ValueError):
        parse_export_language("nope", strict=True)


@pytest.mark.unit
def test_is_rtl_and_document_attrs():
    assert is_rtl("ar") is True
    assert is_rtl("he") is True
    assert is_rtl("fr") is False
    assert uses_arabic_font("ar") is True
    assert uses_arabic_font("fa") is True
    assert uses_arabic_font("he") is False
    assert rtl_document_attrs("ar") == {"lang": "ar", "dir": "rtl"}
    assert rtl_document_attrs("en") == {"lang": "en", "dir": "ltr"}
    assert "Tajawal" not in rtl_css("ar")
    assert "text-align: justify" in rtl_css("ar")
    assert "text-align: justify" in rtl_css("he")
    assert rtl_css("en") == ""


@pytest.mark.unit
def test_localized_form_item_prefers_bank_without_translations():
    from types import SimpleNamespace

    from plugins.upr_visuals.i18n import localized_form_item_label, localized_indicator_label

    bank = SimpleNamespace(name="People reached with climate activities", name_translations=None)
    item = SimpleNamespace(
        label="Climate people",
        label_translations=None,
        custom_label=None,
        indicator_bank=bank,
    )
    assert localized_indicator_label(bank) == "People reached with climate activities"
    assert localized_form_item_label(item) == "People reached with climate activities"


@pytest.mark.unit
def test_localized_form_item_uses_locale_translation(monkeypatch):
    from types import SimpleNamespace

    from plugins.upr_visuals.i18n import localized_form_item_label

    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "fr")
    bank = SimpleNamespace(name="People reached with climate activities", name_translations=None)
    item = SimpleNamespace(
        label="Climate people",
        label_translations={"fr": "Personnes atteintes climat"},
        custom_label=None,
        indicator_bank=bank,
    )
    assert localized_form_item_label(item) == "Personnes atteintes climat"


@pytest.mark.unit
def test_t_and_batch_noop_for_english(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "en")
    assert t("People reached") == "People reached"
    assert t_batch(["A", "B"]) == ["A", "B"]


@pytest.mark.unit
def test_t_system_language_uses_visual_catalog(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "fr")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: True)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("system languages must not call the translation API")

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate", fail_if_called)
    monkeypatch.setattr("flask_babel.gettext", lambda text: f"PO:{text}")
    assert t("People reached") == "Personnes atteintes"
    assert t("Financial Overview") == "Aperçu financier"
    assert t("Strategic Priorities") == "Priorités stratégiques"
    assert t("Enabling Functions") == "Fonctions habilitantes"
    assert t("Bilateral Support") == "Soutien bilatéral"
    assert t("Emergency 1") == "Urgence 1"
    assert t("2026 IFRC network country plan") == "Plan pays du réseau IFRC 2026"
    assert t("A nonce string XYZ-upr") == "PO:A nonce string XYZ-upr"


@pytest.mark.unit
def test_visual_string_tables_cover_each_language():
    from plugins.upr_visuals.strings import VISUAL_STRINGS, lookup_visual_string

    keys = set(VISUAL_STRINGS["fr"])
    for lang, table in VISUAL_STRINGS.items():
        assert set(table) == keys
        assert lookup_visual_string("Emergency 2", lang)
        assert lookup_visual_string("2026-2028 IFRC network country plan", lang)
        assert lookup_visual_string("Unified Country Report", lang)
    assert lookup_visual_string("People reached", "de") is None


@pytest.mark.unit
def test_formatters_and_render_use_visual_catalog(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "fr")
    monkeypatch.setattr("plugins.upr_visuals.render.current_export_language", lambda: "fr")
    from plugins.upr_visuals.formatters import document_subtitle, format_count
    from plugins.upr_visuals.render import render_dashboard_html

    assert format_count(None) == "Non communiqué"
    assert document_subtitle("plan", "2026", plan_years=[2026, 2027, 2028]) == (
        "Plan pays du réseau IFRC 2026-2028"
    )
    html = render_dashboard_html(
        {
            "meta": {
                "kind": "report",
                "national_society": "Uganda Red Cross Society",
                "country_name": "Uganda",
                "iso2": "UG",
                "document_subtitle": "2025 IFRC network annual report, Jan-Dec",
                "header_date": "2 July 2026",
            },
            "kpis": {},
            "strategic_priorities": [],
            "financial": {"ifrc_network": {}, "national_society": {}, "sources": []},
        },
        "combined",
    )
    assert "OUGANDA" in html
    assert ">UGANDA<" not in html
    assert "APERÇU FINANCIER" in html
    assert "FINANCIAL OVERVIEW" not in html
    assert "en francs suisses (CHF)" in html
    assert "dir='ltr'" in html


@pytest.mark.unit
def test_render_dashboard_sets_rtl_dir_for_arabic(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    from plugins.upr_visuals.render import render_dashboard_html

    html = render_dashboard_html(
        {
            "meta": {
                "kind": "report",
                "country_name": "Uganda",
                "iso2": "UG",
                "document_subtitle": "x",
                "header_date": "2 July 2026",
            },
            "kpis": {},
        },
        "combined",
    )
    assert "dir='rtl'" in html
    assert "lang='ar'" in html
    assert "upr-arabic-font" in html
    assert 'class="upr-dashboard upr-dashboard--combined upr-arabic-font"' in html
    assert "upr-doc-footer upr-arabic-font" in html
    assert "بالفرنك السويسري (CHF)" in html
    assert "بالفرنك السويسري (فرنك سويسري)" not in html
    support = render_dashboard_html(
        {
            "meta": {
                "kind": "report",
                "country_name": "Uganda",
                "iso2": "UG",
                "document_subtitle": "x",
                "header_date": "2 July 2026",
                "support_title": "Bilateral support",
            },
            "support": [{"name": "Danish Red Cross", "funding_display": "1.2 مليون", "areas": {}}],
            "support_total": {"value": 1_200_000, "display": "1.2 مليون"},
        },
        "support",
    )
    assert "upr-amt__unit" in support
    assert support.find("upr-amt__unit") < support.find("upr-amt__num")
    assert ">مليون فرنك سويسري<" in support or ">مليون فرنك سويسري</span>" in support
    assert ">1.2<" in support
    assert "CHF 1.2" not in support
    assert "upr-support-total" in support
    assert "dir='ltr'" in support[support.find("upr-support-total") :]
    assert "upr-support-total' colspan=" in support[support.find("upr-support-total-row") :]
    body = support[support.find("<tbody>") : support.find("</tbody>")]
    assert body.find("upr-dot-cell") < body.find("upr-ns")


@pytest.mark.unit
def test_hebrew_is_rtl_without_arabic_font(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "he")
    from plugins.upr_visuals.render import render_dashboard_html

    html = render_dashboard_html(
        {
            "meta": {
                "kind": "report",
                "country_name": "Uganda",
                "iso2": "UG",
                "document_subtitle": "x",
                "header_date": "2 July 2026",
            },
            "kpis": {},
        },
        "combined",
    )
    assert "dir='rtl'" in html
    assert "lang='he'" in html
    assert "upr-arabic-font" not in html


@pytest.mark.unit
def test_rtl_financial_network_puts_bars_left_of_labels(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    from plugins.upr_visuals.render import render_dashboard_html

    html = render_dashboard_html(
        {
            "meta": {
                "kind": "report",
                "country_name": "Uganda",
                "iso2": "UG",
                "document_subtitle": "x",
                "header_date": "2 July 2026",
            },
            "financial": {
                "sources": [
                    {
                        "entity": "IFRC Secretariat",
                        "label": "أمانة الاتحاد الدولي",
                        "value": 0,
                        "display": "غير مُبلَّغ",
                    }
                ],
                "network_entities": [
                    {
                        "entity": "Country",
                        "label": "البلد",
                        "buckets": [
                            {
                                "key": "overall",
                                "label": "",
                                "metrics": [
                                    {
                                        "key": "funding",
                                        "label": "التمويل",
                                        "value": 97_100_000,
                                        "display": "97.1 مليون",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        },
        "financial",
    )
    assert html.find("upr-fin-net__plot") < html.find("upr-fin-net__entity")
    assert html.find("upr-fin-net-col-plot") < html.find("upr-fin-net-col-entity")
    hero = html[html.find("upr-fin-hero") : html.find("upr-fin-network")]
    assert hero.find("upr-bar-plot") < hero.find("upr-bar-label")
    assert hero.find("upr-fin-col-overview-plot") < hero.find("upr-fin-col-overview-label")
    assert hero.find("upr-fin-col-source-plot") < hero.find("upr-fin-col-source-label")
    assert "upr-block__title--center" in html
    assert "upr-amt__unit" in html
    assert html.find("upr-amt__unit") < html.find("upr-amt__num")
    unit = html[html.find("upr-amt__unit") : html.find("upr-amt__num")]
    assert "مليون" in unit
    assert "97.1" not in unit


@pytest.mark.unit
def test_parse_progress_id_and_store():
    assert parse_progress_id("abc-123") == "abc-123"
    assert parse_progress_id("../x") == ""
    assert parse_progress_id("x" * 80) == ""
    start_visuals_progress("job-1")
    update_visuals_progress("job-1", done=3, total=10, lang="de", elapsed=4)
    rec = get_visuals_progress("job-1")
    assert rec["done"] == 3
    assert rec["total"] == 10
    assert rec["pending"] == 7
    assert rec["lang"] == "de"
    assert rec["elapsed"] == 4


@pytest.mark.unit
def test_can_machine_translate_fails_closed(monkeypatch):
    import plugins.upr_visuals.i18n as i18n

    monkeypatch.setattr(i18n, "is_system_language", lambda lang=None: False)
    real_import = __import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app.services.translation.auto_translator":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", guarded)
    assert i18n.can_machine_translate("de") is False


@pytest.mark.unit
def test_localize_export_batches_non_system_language(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "de")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: False)
    batches = []

    def fake_batch(texts, lang):
        assert lang == "de"
        batches.append(list(texts))
        return [f"DE:{item}" for item in texts]

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fake_batch)

    def fail_single(*_args, **_kwargs):
        raise AssertionError("localize_export should batch, not call t() one-by-one")

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate", fail_single)
    progress = []
    builds = []

    def work():
        builds.append(1)
        return [t("People reached"), t("People reached"), t("Not reported")]

    out = localize_export(work, on_progress=lambda **kw: progress.append((kw["done"], kw["total"])))
    assert out == ["DE:People reached", "DE:People reached", "DE:Not reported"]
    assert batches == [["People reached", "Not reported"]]
    assert len(builds) == 2
    assert progress[0][1] == 2
    assert progress[-1] == (2, 2)


@pytest.mark.unit
def test_localize_export_skips_system_language(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: True)
    builds = []

    def fail_batch(*_args, **_kwargs):
        raise AssertionError("system languages must not batch-MT")

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fail_batch)

    def work():
        builds.append(1)
        return t("All visuals")

    assert localize_export(work) == "جميع الرسوم"
    assert builds == [1]


@pytest.mark.unit
def test_unsupported_language_skips_live_mt(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "rm")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: False)
    assert can_machine_translate("rm") is False

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("unsupported languages must not call the translation API")

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate", fail_if_called)
    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fail_if_called)
    assert t("Not reported") == "Not reported"
    assert t_batch(["Not reported", "Country"]) == ["Not reported", "Country"]
    builds = []

    def work():
        builds.append(1)
        return t("Not reported")

    assert localize_export(work) == "Not reported"
    assert builds == [1]


@pytest.mark.unit
def test_t_uses_translator_for_other_languages(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "de")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: False)

    def fake_translate(text, lang):
        assert lang == "de"
        return f"DE:{text}"

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate", fake_translate)
    assert t("People reached") == "DE:People reached"


@pytest.mark.unit
def test_localized_country_uses_babel_territory(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "fr")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: True)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("system languages must not call the translation API")

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate", fail_if_called)
    country = SimpleNamespace(name="Uganda", iso2="UG", name_translations=None)
    assert localized_country_name(country) == "Ouganda"
    assert localized_country_name(iso2="UG", fallback="Uganda") == "Ouganda"
    assert localized_country_header({"country_name": "Uganda", "iso2": "UG"}) == "OUGANDA"


@pytest.mark.unit
def test_localized_country_prefers_stored_translation(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "fr")
    country = SimpleNamespace(
        name="Uganda",
        iso2="UG",
        name_translations={"fr": "Ouganda (stocké)"},
    )
    assert localized_country_name(country) == "Ouganda (stocké)"


@pytest.mark.unit
def test_localized_ns_uses_stored_translation(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "fr")
    ns = SimpleNamespace(
        name="The Netherlands Red Cross",
        name_translations={"fr": "Croix-Rouge néerlandaise", "es": "Cruz Roja Neerlandesa"},
    )
    assert localized_ns_display_name(ns) == "Croix-Rouge néerlandaise"
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "en")
    assert localized_ns_display_name(ns) == "Netherlands Red Cross"


@pytest.mark.unit
def test_localized_ns_machine_translates_other_languages(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "de")
    monkeypatch.setattr("plugins.upr_visuals.i18n.is_system_language", lambda lang=None: False)
    monkeypatch.setattr("plugins.upr_visuals.i18n.t", lambda text: f"DE:{text}")
    ns = SimpleNamespace(name="The Netherlands Red Cross", name_translations={"fr": "Croix-Rouge néerlandaise"})
    assert localized_ns_display_name(ns) == "DE:Netherlands Red Cross"


@pytest.mark.unit
def test_t_batch_and_styled_blocks(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "es")
    calls = []

    def fake_batch(texts, lang):
        assert lang == "es"
        calls.append(list(texts))
        return [f"ES:{item}" for item in texts]

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fake_batch)
    blocks = [
        {"style": "Body", "text": "Context", "runs": [{"text": "Context", "href": "", "bold": False}]},
        {"style": "Blank", "text": "", "runs": [{"text": " ", "href": "", "bold": False}]},
        {
            "kind": "table",
            "rows": [[[{"text": "Label", "runs": [{"text": "Label", "href": "https://x", "bold": False}]}]]],
        },
    ]
    translate_styled_blocks(blocks)
    # Only the two run texts reach the MT engine -- block["text"] is never sent on its own.
    assert calls == [["Context", "Label"]]
    assert blocks[0]["text"] == "ES:Context"
    assert blocks[0]["runs"][0]["text"] == "ES:Context"
    assert blocks[1]["text"] == ""
    assert blocks[2]["rows"][0][0][0]["text"] == "ES:Label"
    assert blocks[2]["rows"][0][0][0]["runs"][0]["href"] == "https://x"


@pytest.mark.unit
def test_translate_styled_blocks_rebuilds_text_from_translated_runs(monkeypatch):
    """block["text"] is never queued for MT; it's rebuilt by joining translated runs."""
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "es")
    calls = []

    def fake_batch(texts, lang):
        calls.append(list(texts))
        return [f"ES:{item}" for item in texts]

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fake_batch)
    blocks = [
        {
            "style": "Body",
            "text": "One two",
            "runs": [
                {"text": "One ", "href": "", "bold": False},
                {"text": "two", "href": "", "bold": True},
            ],
        },
    ]
    translate_styled_blocks(blocks)
    # The paragraph's own text is never one of the MT inputs (only its 2 runs are).
    assert calls == [["One ", "two"]]
    assert blocks[0]["runs"][0]["text"] == "ES:One "
    assert blocks[0]["runs"][1]["text"] == "ES:two"
    assert blocks[0]["text"] == "ES:One ES:two"


@pytest.mark.unit
def test_translate_styled_blocks_dedupes_repeated_runs(monkeypatch):
    """Repeated headings/labels/org names are translated once, like localize_export."""
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "es")
    calls = []

    def fake_batch(texts, lang):
        calls.append(list(texts))
        return [f"ES:{item}" for item in texts]

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fake_batch)
    blocks = [
        {"style": "Body", "text": "Repeat me", "runs": [{"text": "Repeat me", "href": "", "bold": False}]},
        {"style": "Body", "text": "Repeat me", "runs": [{"text": "Repeat me", "href": "", "bold": False}]},
        {"style": "Body", "text": "Unique", "runs": [{"text": "Unique", "href": "", "bold": False}]},
    ]
    translate_styled_blocks(blocks)
    # "Repeat me" is sent to the MT engine exactly once despite appearing twice.
    assert calls == [["Repeat me", "Unique"]]
    assert blocks[0]["text"] == "ES:Repeat me"
    assert blocks[1]["text"] == "ES:Repeat me"
    assert blocks[2]["text"] == "ES:Unique"


@pytest.mark.unit
def test_t_batch_reports_chunk_progress(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    monkeypatch.setattr("plugins.upr_visuals.i18n._T_BATCH_CHUNK", 2)
    batches = []

    def fake_batch(texts, lang):
        assert lang == "ar"
        batches.append(list(texts))
        return [f"AR:{item}" for item in texts]

    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fake_batch)
    progress = []
    out = t_batch(
        ["a", "b", "c", "d", "e"],
        on_progress=lambda **kw: progress.append((kw["done"], kw["total"])),
    )
    assert out == ["AR:a", "AR:b", "AR:c", "AR:d", "AR:e"]
    assert batches == [["a", "b"], ["c", "d"], ["e"]]
    assert progress[0] == (0, 5)
    assert progress[-1] == (5, 5)
    assert (2, 5) in progress
    assert (4, 5) in progress


@pytest.mark.unit
def test_t_batch_uses_cached_chunks(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    monkeypatch.setattr("plugins.upr_visuals.i18n._T_BATCH_CHUNK", 2)
    cache_lookups = []

    def fake_cache(texts, lang):
        cache_lookups.append(list(texts))
        return {"a": "CACHED"}

    called = []

    def fake_batch(texts, lang):
        called.append(list(texts))
        return [f"AR:{item}" for item in texts]

    monkeypatch.setattr("plugins.upr_visuals.i18n._cached_translations", fake_cache)
    monkeypatch.setattr("plugins.upr_visuals.i18n._machine_translate_batch", fake_batch)
    progress = []
    out = t_batch(
        ["a", "b", "c"],
        on_progress=lambda **kw: progress.append((kw["done"], kw["total"])),
    )
    assert out == ["CACHED", "AR:b", "AR:c"]
    # One batched lookup for the whole chunk, not one call per text.
    assert cache_lookups == [["a", "b", "c"]]
    assert called == [["b", "c"]]
    assert progress[0] == (1, 3)
    assert progress[-1] == (3, 3)


@pytest.mark.unit
def test_raster_wrap_sets_rtl_html(monkeypatch):
    monkeypatch.setattr("plugins.upr_visuals.i18n.current_export_language", lambda: "ar")
    from plugins.upr_visuals.raster import _wrap

    html = _wrap(
        "<div class='upr-dashboard'>x</div>",
        dashboard_id="combined",
        title="أفغانستان — Unified Country Report",
    )
    assert "<title>أفغانستان — Unified Country Report</title>" in html
    assert "lang='ar'" in html
    assert "dir='rtl'" in html
    assert "class='upr-arabic-font'" in html
    assert "Tajawal" in html
    assert "html, body { font-family: \"Tajawal\"" in html
    assert "html, body, table, th, td, p, h1, h2, h3, h4, li" not in html
    assert ".upr-arabic-font *" in html
    assert "@bottom-center" in html
    assert "fonts.googleapis.com" not in html
    assert "html[dir=\"rtl\"] .upr-fin-grid" in html
    from plugins.upr_visuals.raster import _rtl_print_css

    rtl = _rtl_print_css("ar")
    assert "table-layout: fixed" in rtl
    assert "overflow: hidden" in rtl
    assert "direction: ltr" in rtl
    assert "html[dir=\"rtl\"] .upr-fin-grid .upr-bar-label" in rtl
    assert "html[dir=\"rtl\"] .upr-block__title," in rtl
    assert "html[dir=\"rtl\"] .upr-block__title--center" in rtl


def _idml_xml_text(data: bytes) -> str:
    import zipfile
    from io import BytesIO

    with zipfile.ZipFile(BytesIO(data)) as zf:
        return "\n".join(
            zf.read(name).decode("utf-8", errors="ignore")
            for name in zf.namelist()
            if name.endswith(".xml")
        )


@pytest.mark.unit
def test_idml_rtl_page_binding():
    from plugins.upr_visuals.idml.xml_idml import Idml

    ltr_doc = Idml(rtl=False)
    rtl_doc = Idml(rtl=True, arabic_font=True)
    table = {
        "kind": "table",
        "rows": [[[{"style": "Body", "text": "A", "runs": [{"text": "A", "href": "", "bold": False}]}]]],
    }
    ltr_doc.styled_story([table])
    rtl_doc.styled_story([table])
    ltr = _idml_xml_text(ltr_doc.package_bytes())
    rtl = _idml_xml_text(rtl_doc.package_bytes())
    assert 'PageBinding="LeftToRight"' in ltr
    assert 'PageBinding="RightToLeft"' in rtl
    assert "Tajawal" in rtl
    assert "RightToLeftDirection" in rtl
    assert "LeftToRightDirection" in ltr
    he_doc = Idml(rtl=True, arabic_font=False)
    he_doc.styled_story([table])
    he = _idml_xml_text(he_doc.package_bytes())
    assert 'PageBinding="RightToLeft"' in he
    assert "<AppliedFont type='string'>Tajawal</AppliedFont>" not in he
    assert "<AppliedFont type='string'>Open Sans</AppliedFont>" in he
