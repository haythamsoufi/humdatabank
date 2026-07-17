"""
Unit tests for app/utils/ws_manager.py – 100% coverage target.

WebSocket connections are fully mocked; no real socket is created.
"""
import json
import time
import pytest
from unittest.mock import MagicMock, patch

from app.utils.ws_manager import (
    WebSocketManager,
    broadcast_notification,
    broadcast_unread_count,
    ws_manager,
)


def _make_ws():
    """Return a mock WebSocket object with a working send()."""
    ws = MagicMock()
    ws.send = MagicMock()
    return ws


# ---------------------------------------------------------------------------
# WebSocketManager – add_connection
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerAddConnection:
    def test_add_single_connection(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        assert mgr.add_connection(1, ws) is True
        assert mgr.get_connection_count(1) == 1

    def test_add_respects_total_limit(self):
        mgr = WebSocketManager(max_total_connections=2)
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
        assert mgr.add_connection(1, ws1) is True
        assert mgr.add_connection(2, ws2) is True
        # Third should be rejected
        assert mgr.add_connection(3, ws3) is False

    def test_add_respects_per_user_limit_and_removes_oldest(self):
        mgr = WebSocketManager(max_connections_per_user=2, max_total_connections=100)
        ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
        mgr.add_connection(1, ws1)
        mgr.add_connection(1, ws2)
        # Third connection for same user: oldest should be removed
        mgr.add_connection(1, ws3)
        assert mgr.get_connection_count(1) == 2
        assert ws1 not in mgr._connection_metadata
        assert ws2 in mgr._connection_metadata
        assert ws3 in mgr._connection_metadata

    def test_fifo_eviction_removes_first_inserted(self):
        mgr = WebSocketManager(max_connections_per_user=2, max_total_connections=100)
        ws1, ws2, ws3, ws4 = _make_ws(), _make_ws(), _make_ws(), _make_ws()
        mgr.add_connection(1, ws1)
        mgr.add_connection(1, ws2)
        mgr.add_connection(1, ws3)  # evicts ws1
        mgr.add_connection(1, ws4)  # evicts ws2
        assert set(mgr._connections[1].keys()) == {ws3, ws4}

    def test_channel_budget_rejects(self):
        mgr = WebSocketManager(
            max_total_connections=10,
            max_connections_per_user=10,
            channel_budgets={'ai_chat': 1, 'notifications': 10, 'ai_docs': 1, 'default': 10},
        )
        ws1, ws2 = _make_ws(), _make_ws()
        assert mgr.add_connection(1, ws1, channel='ai_chat') is True
        assert mgr.add_connection(2, ws2, channel='ai_chat') is False
        assert mgr.add_connection(2, ws2, channel='notifications') is True

    def test_snapshot_includes_channel_budgets(self):
        mgr = WebSocketManager(max_total_connections=5, channel_budgets={'notifications': 5, 'ai_chat': 2, 'ai_docs': 1, 'default': 5})
        ws = _make_ws()
        mgr.add_connection(1, ws, channel='notifications')
        snap = mgr.snapshot()
        assert snap['by_channel']['notifications'] == 1
        assert snap['channel_budgets']['ai_chat'] == 2

    def test_metadata_stored_on_add(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        assert ws in mgr._connection_metadata
        assert mgr._connection_metadata[ws]['user_id'] == 1
        assert 'created_at' in mgr._connection_metadata[ws]

    def test_add_returns_true(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        result = mgr.add_connection(42, ws)
        assert result is True


# ---------------------------------------------------------------------------
# WebSocketManager – remove_connection
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerRemoveConnection:
    def test_remove_existing_connection(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        mgr.remove_connection(1, ws)
        assert mgr.get_connection_count(1) == 0

    def test_remove_last_connection_cleans_up_user_entry(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        mgr.remove_connection(1, ws)
        assert 1 not in mgr._connections

    def test_remove_nonexistent_connection_is_safe(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        # Should not raise
        mgr.remove_connection(999, ws)

    def test_remove_clears_metadata(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        mgr.remove_connection(1, ws)
        assert ws not in mgr._connection_metadata


# ---------------------------------------------------------------------------
# WebSocketManager – update_activity
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerUpdateActivity:
    def test_updates_last_activity_and_count(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        initial_count = mgr._connection_metadata[ws]['message_count']
        mgr.update_activity(ws)
        assert mgr._connection_metadata[ws]['message_count'] == initial_count + 1

    def test_update_nonexistent_connection_is_safe(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        # ws never added – should not raise
        mgr.update_activity(ws)


# ---------------------------------------------------------------------------
# WebSocketManager – send_to_user
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerSendToUser:
    def test_send_to_nonexistent_user_returns_zero(self):
        mgr = WebSocketManager()
        result = mgr.send_to_user(999, 'test', {})
        assert result == 0

    def test_send_returns_successful_count(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        result = mgr.send_to_user(1, 'event', {'key': 'val'})
        assert result == 1

    def test_send_calls_ws_send_with_json(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        mgr.send_to_user(1, 'ping', {'x': 1})
        ws.send.assert_called_once()
        payload = json.loads(ws.send.call_args[0][0])
        assert payload['type'] == 'ping'
        assert payload['data'] == {'x': 1}

    def test_broken_connection_removed_after_send(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        ws.send.side_effect = Exception('broken')
        mgr.add_connection(1, ws)
        result = mgr.send_to_user(1, 'event', {})
        assert result == 0
        assert mgr.get_connection_count(1) == 0

    def test_send_to_multiple_connections(self):
        mgr = WebSocketManager(max_connections_per_user=10)
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.add_connection(1, ws1)
        mgr.add_connection(1, ws2)
        result = mgr.send_to_user(1, 'event', {})
        assert result == 2

    def test_unexpected_exception_returns_zero(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        # Patch utcnow (used inside send_to_user before the per-ws try block)
        with patch('app.utils.ws_manager.utcnow', side_effect=Exception('utcnow failed')):
            result = mgr.send_to_user(1, 'event', {})
        assert result == 0


# ---------------------------------------------------------------------------
# WebSocketManager – send_to_connection
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerSendToConnection:
    def test_send_returns_true_on_success(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        result = mgr.send_to_connection(ws, 'event', {'a': 1})
        assert result is True

    def test_send_calls_ws_send(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        mgr.send_to_connection(ws, 'ping', {})
        ws.send.assert_called_once()

    def test_broken_connection_returns_false_and_removes(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        ws.send.side_effect = Exception('broken')
        mgr.add_connection(1, ws)
        result = mgr.send_to_connection(ws, 'event', {})
        assert result is False
        assert mgr.get_connection_count(1) == 0

    def test_broken_connection_not_in_manager_returns_false(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        ws.send.side_effect = Exception('broken')
        # ws was never added
        result = mgr.send_to_connection(ws, 'event', {})
        assert result is False


# ---------------------------------------------------------------------------
# WebSocketManager – get_connection_count
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerGetConnectionCount:
    def test_total_count_across_users(self):
        mgr = WebSocketManager(max_total_connections=100)
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.add_connection(1, ws1)
        mgr.add_connection(2, ws2)
        assert mgr.get_connection_count() == 2

    def test_per_user_count(self):
        mgr = WebSocketManager()
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.add_connection(1, ws1)
        mgr.add_connection(2, ws2)
        assert mgr.get_connection_count(1) == 1
        assert mgr.get_connection_count(2) == 1

    def test_nonexistent_user_count_zero(self):
        mgr = WebSocketManager()
        assert mgr.get_connection_count(999) == 0


# ---------------------------------------------------------------------------
# WebSocketManager – get_all_user_ids
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerGetAllUserIds:
    def test_empty_returns_empty_set(self):
        mgr = WebSocketManager()
        assert mgr.get_all_user_ids() == set()

    def test_returns_connected_user_ids(self):
        mgr = WebSocketManager(max_total_connections=100)
        ws1, ws2 = _make_ws(), _make_ws()
        mgr.add_connection(1, ws1)
        mgr.add_connection(2, ws2)
        assert mgr.get_all_user_ids() == {1, 2}


# ---------------------------------------------------------------------------
# WebSocketManager – cleanup_stale_connections
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWebSocketManagerCleanupStaleConnections:
    def test_no_stale_connections_returns_zero(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        cleaned = mgr.cleanup_stale_connections(max_idle_seconds=300)
        assert cleaned == 0

    def test_stale_connection_removed(self):
        mgr = WebSocketManager()
        ws = _make_ws()
        mgr.add_connection(1, ws)
        # Simulate old last_activity
        mgr._connection_metadata[ws]['last_activity'] = time.time() - 400
        cleaned = mgr.cleanup_stale_connections(max_idle_seconds=300)
        assert cleaned == 1
        assert mgr.get_connection_count(1) == 0


# ---------------------------------------------------------------------------
# broadcast_notification
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestBroadcastNotification:
    def test_no_app_context_returns_false(self):
        result = broadcast_notification(1, {'msg': 'hello'})
        assert result is False

    def test_websocket_disabled_returns_false(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = False
            result = broadcast_notification(1, {'msg': 'hello'})
            assert result is False
            app.config['WEBSOCKET_ENABLED'] = True

    def test_sends_when_user_has_connection(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = True
            ws = _make_ws()
            ws_manager.add_connection(1, ws)
            try:
                result = broadcast_notification(1, {'title': 'Test'})
                assert result is True
                ws.send.assert_called_once()
            finally:
                ws_manager.remove_connection(1, ws)

    def test_returns_false_when_no_ws_connection(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = True
            result = broadcast_notification(99999, {'title': 'Test'})
            assert result is False

    def test_exception_during_send_returns_false(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = True
            with patch.object(ws_manager, 'send_to_user', side_effect=Exception('boom')):
                result = broadcast_notification(1, {'title': 'Test'})
                assert result is False


# ---------------------------------------------------------------------------
# broadcast_unread_count
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestBroadcastUnreadCount:
    def test_no_app_context_returns_false(self):
        result = broadcast_unread_count(1, 5)
        assert result is False

    def test_websocket_disabled_returns_false(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = False
            result = broadcast_unread_count(1, 3)
            assert result is False
            app.config['WEBSOCKET_ENABLED'] = True

    def test_sends_unread_count_when_connected(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = True
            ws = _make_ws()
            ws_manager.add_connection(2, ws)
            try:
                result = broadcast_unread_count(2, 7)
                assert result is True
                sent_payload = json.loads(ws.send.call_args[0][0])
                assert sent_payload['data']['unread_count'] == 7
            finally:
                ws_manager.remove_connection(2, ws)

    def test_returns_false_when_no_connection(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = True
            result = broadcast_unread_count(99998, 0)
            assert result is False

    def test_exception_during_send_returns_false(self, app):
        with app.app_context():
            app.config['WEBSOCKET_ENABLED'] = True
            with patch.object(ws_manager, 'send_to_user', side_effect=Exception('boom')):
                result = broadcast_unread_count(1, 3)
                assert result is False
