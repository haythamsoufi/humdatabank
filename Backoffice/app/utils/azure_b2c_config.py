"""Azure AD B2C (OIDC) configuration detection — shared by auth and admin routes."""

from __future__ import annotations

from flask import Flask, current_app


def is_azure_b2c_configured(app: Flask | None = None) -> bool:
    """
    Return True when all required Azure AD B2C env-driven settings are present.

    Same semantics as user_management ``_is_azure_sso_enabled`` (four keys must be truthy).
    """
    cfg = app if app is not None else current_app
    return bool(
        cfg.config.get("AZURE_B2C_TENANT")
        and cfg.config.get("AZURE_B2C_POLICY")
        and cfg.config.get("AZURE_B2C_CLIENT_ID")
        and cfg.config.get("AZURE_B2C_CLIENT_SECRET")
    )
