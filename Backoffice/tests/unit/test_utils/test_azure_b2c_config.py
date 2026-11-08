"""Unit tests for Azure B2C config detection (no database)."""

from flask import Flask

from app.utils.azure_b2c_config import is_azure_b2c_configured


def test_is_azure_b2c_configured_false_when_keys_missing():
    app = Flask(__name__)
    assert is_azure_b2c_configured(app) is False


def test_is_azure_b2c_configured_true_when_all_keys_set():
    app = Flask(__name__)
    app.config.update(
        AZURE_B2C_TENANT="contoso.onmicrosoft.com",
        AZURE_B2C_POLICY="B2C_1_signup",
        AZURE_B2C_CLIENT_ID="client",
        AZURE_B2C_CLIENT_SECRET="secret",
    )
    assert is_azure_b2c_configured(app) is True
