"""Strict check: merged catalog covers every candidate (method, endpoint) from url_map."""

from app import create_app
from app.utils.activity_logging_skip import (
    should_exclude_from_activity_catalog,
    should_skip_activity_path,
)
from app.utils.activity_endpoint_overrides import (
    resolve_delete_activity_type,
    resolve_post_activity_type,
)
from app.utils.activity_endpoint_catalog import ENDPOINT_ACTIVITY_SPECS
from app.utils.activity_endpoint_catalog.spec import lookup_activity_endpoint_spec


def test_get_handlers_excluded_from_catalog_coverage():
    assert should_exclude_from_activity_catalog("GET", "admin_notifications.api_get_all_notifications")
    assert should_exclude_from_activity_catalog("GET", "admin_notifications.notifications_center")
    assert not should_exclude_from_activity_catalog("POST", "admin_notifications.api_send_notifications")


def test_activity_catalog_has_no_gaps_vs_url_map():
    app = create_app()
    expected: set[tuple[str, str]] = set()
    with app.app_context():
        for rule in app.url_map.iter_rules():
            ep = rule.endpoint
            if not ep:
                continue
            if should_skip_activity_path(str(rule.rule or "")):
                continue
            if ep == "forms.enter_data":
                continue
            if ep in ("favicon", "test_static_file"):
                continue
            methods = set(rule.methods or ()) - {"HEAD", "OPTIONS", "TRACE"}
            for method in sorted(methods):
                if should_exclude_from_activity_catalog(method, ep):
                    continue
                if ep == "main.dashboard" and method == "POST":
                    continue
                if method == "POST" and resolve_post_activity_type(ep):
                    continue
                if method == "DELETE" and resolve_delete_activity_type(ep):
                    continue
                expected.add((method, ep))

    missing: list[tuple[str, str]] = []
    for key in sorted(expected):
        if lookup_activity_endpoint_spec(key[0], key[1], ENDPOINT_ACTIVITY_SPECS) is None:
            missing.append(key)

    assert not missing, f"Catalog missing {len(missing)} keys, e.g. {missing[:10]}"
