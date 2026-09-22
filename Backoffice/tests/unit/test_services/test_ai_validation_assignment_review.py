"""Unit tests for app.services.ai.validation.assignment_review._fallback_review.

Covers the "overview_figures tile only for a fully-'ok' check" policy: a flagged or
highlighted check must never also get a tile (it already has a full sentence in
"Needs attention"), while an "ok" check keeps its tile so the number is visible at a
glance without expanding the collapsed "In good shape" list. See KNOWLEDGE.md
("Division of labour: deterministic pack vs LLM") and the module docstring on
app/services/ai/validation/assignment_review.py for the policy this guards.
"""
from app.services.ai.validation.assignment_review import _fallback_review


def _pack(figures=None, ok=None, flags=None, highlights=None, comment_text=""):
    ok = ok or []
    flags = flags or []
    highlights = highlights or []
    return {
        "figures": figures or {},
        "ok": ok,
        "flags": flags,
        "highlights": highlights,
        "findings": ok + flags + highlights,
        "comment_text": comment_text,
    }


class TestOverviewFiguresOkOnlyGating:
    def test_flagged_people_longer_term_gets_no_tile(self):
        pack = _pack(
            figures={
                "people_longer_term": {
                    "status": "flag",
                    "grand_total": 14,
                    "nonzero_count": 8,
                    "cell_count": 15,
                    "implausible_small": True,
                },
            },
            flags=[{
                "severity": "flag",
                "label": "Longer-term people to be reached",
                "text": "The longer-term people-to-be-reached numbers look far too small...",
                "form_item_id": 954,
            }],
        )
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == []
        # The full sentence must still be there for the user to read — just not duplicated as a tile.
        assert len(result["whats_not"]) == 1
        assert result["whats_not"][0]["label"] == "Longer-term people to be reached"

    def test_ok_people_longer_term_gets_a_tile_without_looks_too_low_suffix(self):
        pack = _pack(figures={
            "people_longer_term": {
                "status": "ok",
                "grand_total": 3733750,
                "nonzero_count": 15,
                "cell_count": 15,
                "implausible_small": False,
            },
        })
        result = _fallback_review(pack, counts={}, headline="")
        assert len(result["overview_figures"]) == 1
        tile = result["overview_figures"][0]
        assert tile["label"] == "Longer-term people to be reached"
        assert "3,733,750 people planned in total (15 of 15 entries filled in)" == tile["value"]
        assert "looks too low" not in tile["value"]

    def test_flagged_ns_key_figures_gets_no_tile(self):
        pack = _pack(
            figures={"ns_key_figures": {"status": "flag", "filled": 0, "total": 4}},
            flags=[{"severity": "flag", "label": "National Society key figures", "text": "empty", "form_item_id": 1}],
        )
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == []

    def test_ok_ns_key_figures_gets_a_tile(self):
        pack = _pack(figures={"ns_key_figures": {"status": "ok", "filled": 4, "total": 4}})
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == [{
            "label": "National Society key figures",
            "value": "4 of 4 completed",
        }]

    def test_highlighted_emergency_appeals_gets_no_tile(self):
        pack = _pack(
            figures={"people_emergency": {
                "status": "highlight",
                "available_count": 1,
                "selected_rows": [],
                "rows_with_values": [],
            }},
            highlights=[{"severity": "highlight", "label": "Emergency Appeals", "text": "1 available, not added", "form_item_id": 960}],
        )
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == []

    def test_ok_emergency_appeals_gets_a_tile(self):
        pack = _pack(figures={"people_emergency": {
            "status": "ok",
            "available_count": 1,
            "selected_rows": ["MDRGM017"],
            "rows_with_values": ["MDRGM017"],
        }})
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == [{
            "label": "Emergency appeals — people to be reached",
            "value": "1 of 1 available emergency reported",
        }]

    def test_flagged_funding_gets_no_tile(self):
        pack = _pack(
            figures={"funding_y0_ifrc": {
                "status": "flag",
                "required_total": 7,
                "required_filled": 5,
                "missing_labels": ["Response - Disasters and crises"],
            }},
            flags=[{"severity": "flag", "label": "Funding Requirements", "text": "missing", "form_item_id": 967}],
        )
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == []

    def test_ok_funding_gets_a_tile(self):
        pack = _pack(figures={"funding_y0_ifrc": {
            "status": "ok",
            "required_total": 7,
            "required_filled": 7,
            "missing_labels": [],
        }})
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == [{
            "label": "IFRC Secretariat funding (this year)",
            "value": "7 of 7 required categories completed",
        }]

    def test_matches_reported_screenshot_three_flags_one_ok_tile(self):
        """Regression for the exact scenario reported: 3 issues need attention, and
        only the passing IFRC Secretariat funding check should still show a tile."""
        pack = _pack(
            figures={
                "people_longer_term": {"status": "flag", "grand_total": 14, "nonzero_count": 8, "cell_count": 15, "implausible_small": True},
                "ns_key_figures": {"status": "flag", "filled": 0, "total": 4},
                "people_emergency": {"status": "flag", "available_count": 1, "selected_rows": [], "rows_with_values": []},
                "funding_y0_ifrc": {"status": "ok", "required_total": 7, "required_filled": 7, "missing_labels": []},
            },
            flags=[
                {"severity": "flag", "label": "Longer-term people to be reached", "text": "...", "form_item_id": 954},
                {"severity": "flag", "label": "National Society key figures", "text": "...", "form_item_id": 1},
                {"severity": "flag", "label": "Emergency Appeals", "text": "...", "form_item_id": 960},
            ],
        )
        result = _fallback_review(pack, counts={}, headline="")
        assert len(result["overview_figures"]) == 1
        assert result["overview_figures"][0]["label"] == "IFRC Secretariat funding (this year)"
        assert len(result["whats_not"]) == 3

    def test_no_status_key_at_all_is_treated_as_not_ok(self):
        """Defensive: a figures sub-dict from an older/unexpected shape without a
        ``status`` key must not accidentally show a tile."""
        pack = _pack(figures={"ns_key_figures": {"filled": 4, "total": 4}})
        result = _fallback_review(pack, counts={}, headline="")
        assert result["overview_figures"] == []
