"""Tests for stable_key sharing across template versions."""

from types import SimpleNamespace

from app.utils.stable_key import (
    T22_FUNDING_MATRIX_STABLE_KEY,
    T22_STAFF_MATRIX_STABLE_KEY,
    is_valid_stable_key,
)
from app.utils.stable_key_backfill import (
    align_stable_key,
    fill_null_stable_keys,
    index_by_position,
    lineage_order,
    shared_key_for_group,
)


def _version(version_id, parent_id=None):
    return SimpleNamespace(id=version_id, based_on_version_id=parent_id)


def _row(row_id, version_id, stable_key=None):
    return SimpleNamespace(id=row_id, version_id=version_id, stable_key=stable_key)


class TestLineageOrder:
    def test_parents_run_before_children(self):
        root = _version(1)
        child = _version(2, 1)
        grandchild = _version(3, 2)
        ordered = lineage_order([grandchild, child])
        assert [version.id for version in ordered] == [2, 3]
        assert root.id == 1


class TestAlignStableKey:
    def test_mints_one_key_when_both_are_null(self):
        source = _row(1, 1)
        target = _row(2, 2)
        assert align_stable_key(source, target, lambda: "shared-key") == "minted"
        assert source.stable_key == "shared-key"
        assert target.stable_key == "shared-key"

    def test_copies_parent_key_onto_null_child(self):
        source = _row(1, 1, "parent-key")
        target = _row(2, 2)
        assert align_stable_key(source, target, lambda: "unused") == "copied"
        assert target.stable_key == "parent-key"

    def test_does_not_overwrite_divergent_keys(self):
        source = _row(1, 1, "parent-key")
        target = _row(2, 2, "child-key")
        assert align_stable_key(source, target, lambda: "unused") == "unchanged"
        assert source.stable_key == "parent-key"
        assert target.stable_key == "child-key"


class TestIndexByPosition:
    def test_drops_ambiguous_positions(self):
        rows = [_row(1, 1), _row(2, 1)]
        indexed = index_by_position(rows, lambda row: row.version_id)
        assert indexed == {}


class TestSharedKeyForGroup:
    def test_reuses_the_existing_key(self):
        assert shared_key_for_group(["keep-me", None], lambda: "new") == "keep-me"

    def test_refuses_a_diverged_group(self):
        assert shared_key_for_group(["a", "b"], lambda: "new") is None


class TestFillNullStableKeys:
    def test_uses_canonical_key_when_group_is_null(self):
        staff = _row(1314, 22)
        updated = fill_null_stable_keys({22: [staff]}, "canonical-staff", lambda: "minted")
        assert updated == 1
        assert staff.stable_key == "canonical-staff"
        assert is_valid_stable_key(T22_STAFF_MATRIX_STABLE_KEY)
        assert is_valid_stable_key(T22_FUNDING_MATRIX_STABLE_KEY)

    def test_copies_existing_key_onto_null_sibling(self):
        published = _row(1314, 22, "already-set")
        draft = _row(2000, 23)
        updated = fill_null_stable_keys(
            {22: [published], 23: [draft]},
            "canonical-staff",
            lambda: "minted",
        )
        assert updated == 1
        assert draft.stable_key == "already-set"
