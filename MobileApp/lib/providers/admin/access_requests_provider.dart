import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../../config/app_config.dart';
import '../../models/admin/country_access_request_item.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';

/// Country access requests via [GET /api/mobile/v1/admin/access-requests] and actions.
class AccessRequestsProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
  final ErrorHandler _errorHandler = ErrorHandler();

  List<CountryAccessRequestItem> _pending = [];
  List<CountryAccessRequestItem> _processed = [];
  bool _autoApproveEnabled = false;
  bool _isLoading = false;
  String? _error;
  bool _actionInFlight = false;

  List<CountryAccessRequestItem> get pending => List.unmodifiable(_pending);
  List<CountryAccessRequestItem> get processed => List.unmodifiable(_processed);
  bool get autoApproveEnabled => _autoApproveEnabled;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get actionInFlight => _actionInFlight;

  Future<void> load({bool showLoading = true}) async {
    if (shouldDeferRemoteFetch) {
      if (showLoading) {
        _isLoading = false;
      }
      notifyListeners();
      return;
    }
    if (showLoading) {
      _isLoading = true;
      _error = null;
      notifyListeners();
    }

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.get(
            AppConfig.mobileAccessRequestsEndpoint,
            useCache: false,
          ),
      context: 'Access requests',
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    if (response == null) {
      _error = 'Unable to load access requests.';
      _pending = [];
      _processed = [];
      if (showLoading) _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 403) {
      _error =
          'You do not have permission to view access requests on the server.';
      _pending = [];
      _processed = [];
      if (showLoading) _isLoading = false;
      notifyListeners();
      return;
    }

    if (response.statusCode == 200) {
      try {
        final decoded = decodeJsonObject(response.body);
        if (mobileResponseIsSuccess(decoded)) {
          final rawData = mobileNestedDataOrRootMap(decoded);
          final p = rawData['pending'];
          final r = rawData['processed'];
          _pending = p is List
              ? p
                  .whereType<Map<String, dynamic>>()
                  .map(CountryAccessRequestItem.fromJson)
                  .toList()
              : [];
          _processed = r is List
              ? r
                  .whereType<Map<String, dynamic>>()
                  .map(CountryAccessRequestItem.fromJson)
                  .toList()
              : [];
          _sortAccessRequestsNewestFirst();
          _autoApproveEnabled = (rawData['auto_approve_enabled'] ?? decoded['auto_approve_enabled']) == true;
          _error = null;
        } else {
          _error = 'Unexpected response from server.';
          _pending = [];
          _processed = [];
        }
      } catch (e, stackTrace) {
        final err = _errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Parse access requests',
        );
        _error = err.getUserMessage();
        _pending = [];
        _processed = [];
      }
    } else {
      _error = 'Unable to load access requests.';
      _pending = [];
      _processed = [];
    }

    if (showLoading) _isLoading = false;
    notifyListeners();
  }

  Future<bool> approve(int requestId) async {
    return _postAction(
      '${AppConfig.mobileAccessRequestsEndpoint}/$requestId/approve',
      contextLabel: 'Approve access request',
    );
  }

  Future<bool> reject(int requestId) async {
    return _postAction(
      '${AppConfig.mobileAccessRequestsEndpoint}/$requestId/reject',
      contextLabel: 'Reject access request',
    );
  }

  Future<bool> _postAction(
    String path, {
    required String contextLabel,
  }) async {
    _actionInFlight = true;
    _error = null;
    notifyListeners();

    final response =
        await _errorHandler.executeWithErrorHandling<http.Response>(
      apiCall: () => _api.post(path, body: {}),
      context: contextLabel,
      defaultValue: null,
      maxRetries: 1,
      handleAuthErrors: true,
    );

    _actionInFlight = false;

    if (response == null) {
      _error = 'Request failed.';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 403) {
      _error = 'You do not have permission for this action.';
      notifyListeners();
      return false;
    }

    if (response.statusCode == 400) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map && decoded['error'] != null) {
          _error = decoded['error'].toString();
        } else {
          _error = 'Request could not be completed.';
        }
      } catch (_) {
        _error = 'Request could not be completed.';
      }
      notifyListeners();
      return false;
    }

    if (response.statusCode != 200) {
      _error = 'Request could not be completed.';
      notifyListeners();
      return false;
    }

    try {
      final decoded = decodeJsonObject(response.body);
      if (mobileResponseIsSuccess(decoded)) {
        await load(showLoading: false);
        return true;
      }
    } catch (_) {}

    await load(showLoading: false);
    return true;
  }

  /// Pending: newest request first. Processed: most recently processed first.
  void _sortAccessRequestsNewestFirst() {
    DateTime? parseIso(String? iso) {
      if (iso == null || iso.isEmpty) return null;
      final normalized = iso.endsWith('Z') ? iso : '${iso}Z';
      return DateTime.tryParse(normalized) ?? DateTime.tryParse(iso);
    }

    int compareDesc(DateTime? a, DateTime? b) {
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return b.compareTo(a);
    }

    _pending.sort(
      (a, b) => compareDesc(parseIso(a.createdAt), parseIso(b.createdAt)),
    );
    _processed.sort(
      (a, b) => compareDesc(
        parseIso(a.processedAt ?? a.createdAt),
        parseIso(b.processedAt ?? b.createdAt),
      ),
    );
  }
}
