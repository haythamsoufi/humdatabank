"""Dashboard sample seed stays quiet when the form tables are not available."""

from unittest.mock import MagicMock, patch


def test_skips_when_assignment_tables_are_missing():
    from app.seeding import _seed_dev_dashboard_samples

    app = MagicMock()
    country = MagicMock()
    country.id = 1
    inspector = MagicMock()
    inspector.has_table.return_value = False

    with patch("app.seeding.inspect", return_value=inspector):
        _seed_dev_dashboard_samples(app, country, "ifrc.org")

    app.logger.info.assert_called()
    assert "not ready" in app.logger.info.call_args[0][0]


def test_skips_when_table_check_is_not_a_real_database():
    from app.seeding import _seed_dev_dashboard_samples

    app = MagicMock()
    country = MagicMock()
    country.id = 1
    inspector = MagicMock()
    inspector.has_table.return_value = MagicMock()

    with patch("app.seeding.inspect", return_value=inspector):
        _seed_dev_dashboard_samples(app, country, "ifrc.org")

    app.logger.info.assert_called()
    assert "not ready" in app.logger.info.call_args[0][0]
