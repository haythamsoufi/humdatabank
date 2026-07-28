"""Unit tests for UPR import label matching helpers."""

import sys
from pathlib import Path

imports_dir = Path(__file__).resolve().parents[2] / "scripts" / "imports"
if str(imports_dir) not in sys.path:
    sys.path.insert(0, str(imports_dir))

from upr_import_versioning import find_item_by_label  # noqa: E402


class TestFindItemByLabel:
    def test_substring_match(self):
        labels = {"optional breakdown by sp/ef (chf)": 1405, "ns total funding": 1403}
        assert find_item_by_label(labels, "optional breakdown by sp/ef") == 1405
        assert find_item_by_label(labels, "ns total funding") == 1403
