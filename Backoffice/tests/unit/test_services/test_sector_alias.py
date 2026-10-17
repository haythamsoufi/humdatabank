from app.services.indicators.remote_sync_service import resolve_sector_alias, rewrite_sector_levels


def test_wash_alias_uses_spelled_out_sector_when_it_exists():
    names = ["Health", "Water, Sanitation, and Hygiene"]
    assert resolve_sector_alias("WASH", names) == "Water, Sanitation, and Hygiene"
    assert resolve_sector_alias("wash", names) == "Water, Sanitation, and Hygiene"


def test_wash_alias_keeps_original_name_when_spelled_out_sector_is_missing():
    assert resolve_sector_alias("WASH", ["Health"]) == "WASH"


def test_unrelated_sector_name_is_unchanged():
    assert resolve_sector_alias("Health", ["Water, Sanitation, and Hygiene"]) == "Health"


def test_rewrite_moves_wash_sector_id_and_drops_duplicate_level():
    updated, changed = rewrite_sector_levels(
        {"primary": 23, "secondary": 3},
        source_id=23,
        target_id=3,
    )
    assert changed is True
    assert updated == {"primary": 3}


def test_rewrite_leaves_other_sectors_untouched():
    payload = {"primary": 7}
    updated, changed = rewrite_sector_levels(payload, source_id=23, target_id=3)
    assert changed is False
    assert updated == payload
