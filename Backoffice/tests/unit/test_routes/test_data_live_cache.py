"""live=true on GET /api/v1/data skips the per-worker dimension caches."""
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.unit]


def test_countries_table_live_skips_worker_cache(app):
    from app.routes.api import data as data_routes

    with patch.object(
        data_routes._countries_table_cache, 'get_or_load', return_value=[{'id': 1}],
    ) as cached_load, patch.object(
        data_routes, '_load_full_countries_table_uncached', return_value=[{'id': 2}],
    ) as live_load:
        assert data_routes._load_full_countries_table() == [{'id': 1}]
        cached_load.assert_called_once()
        live_load.assert_not_called()
        assert data_routes._load_full_countries_table(live=True) == [{'id': 2}]
        live_load.assert_called_once()
        assert cached_load.call_count == 1
