import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[3] / "scripts" / "ops" / "sync_storage_from_prod.py"
_spec = importlib.util.spec_from_file_location("sync_storage_from_prod", _PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
blobs_to_copy = _module.blobs_to_copy
static_prefixes_for = _module.static_prefixes_for


def test_copies_only_blobs_missing_on_the_destination():
    planned = blobs_to_copy(
        {"system/sectors/WASH_sector.png", "resources/report.pdf"},
        {"resources/report.pdf"},
        overwrite=False,
    )
    assert planned == ["system/sectors/WASH_sector.png"]


def test_overwrite_copies_blobs_that_already_exist():
    planned = blobs_to_copy(
        {"system/sectors/WASH_sector.png"},
        {"system/sectors/WASH_sector.png"},
        overwrite=True,
    )
    assert planned == ["system/sectors/WASH_sector.png"]


def test_ns_logo_prefix_narrows_the_public_cdn_copy():
    assert static_prefixes_for(("system/ns/",), prefixes_were_explicit=True) == ("system/ns/",)


def test_default_cdn_copy_includes_ns_logos_with_other_system_icons():
    assert static_prefixes_for(("system/", "resources/"), prefixes_were_explicit=False) == ("system/",)
