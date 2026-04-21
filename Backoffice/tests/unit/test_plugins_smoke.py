import pytest


@pytest.mark.unit
def test_plugin_entry_templates_render_smoke(app):
    """
    Smoke test:
    - render an entry template for each active plugin field type
    - verify deterministic DOM markers exist
    - verify ES module config is present
    """
    plugin_manager = getattr(app, "plugin_manager", None)
    form_integration = getattr(app, "form_integration", None)

    assert plugin_manager is not None, "plugin_manager not initialized in app"
    assert form_integration is not None, "form_integration not initialized in app"

    # Stable field id for DOM checks
    field_id = "test123"

    active_field_types = plugin_manager.list_active_field_types()
    assert active_field_types, "No active plugin field types discovered"

    for field_type in active_field_types:
        cfg = plugin_manager.get_field_type_config(field_type) or {}
        entry_cfg = cfg.get("entry_form_config") or {}

        # JS module contract
        assert entry_cfg.get("es_module_path"), f"{field_type}: missing es_module_path"
        assert entry_cfg.get("es_module_class"), f"{field_type}: missing es_module_class"

        html = form_integration.render_custom_field_entry_form(
            field_type=field_type,
            field_config={},
            field_value={},
            field_id=field_id,
            can_edit=True,
            country_iso="TST",
        )
        assert isinstance(html, str) and html.strip(), f"{field_type}: template rendered empty"

        # Deterministic DOM: at least one of these should be true across plugins
        dom_ok = (
            f'data-field-id="{field_id}"' in html
            or f'id="map-{field_id}"' in html
            or f'id="field-{field_id}"' in html
            or f'name="{field_id}"' in html
        )
        assert dom_ok, f"{field_type}: rendered HTML missing expected DOM marker for field_id={field_id}"
