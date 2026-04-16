import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../models/public/leaderboard_entry.dart';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';

/// Leaderboard provider that manages leaderboard data
class LeaderboardProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();

  List<LeaderboardEntry> _leaderboard = [];
  bool _isLoading = false;
  String? _error;

  List<LeaderboardEntry> get leaderboard => _leaderboard;
  bool get isLoading => _isLoading;
  String? get error => _error;

  /// Load leaderboard from backend
  Future<void> loadLeaderboard({int limit = 5}) async {
    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _apiService.get(
        AppConfig.mobileQuizLeaderboardEndpoint,
        queryParams: {'limit': limit.toString()},
        // Matches Backoffice: GET /data/quiz/leaderboard uses @mobile_auth_required
        // (same module as submit-score; scores are attributed to users).
        includeAuth: true,
      );

      if (response.statusCode == 200) {
        final data = response.body;
        final jsonData = jsonDecode(data) as Map<String, dynamic>;

        if (jsonData['success'] == true) {
          final rawData = jsonData['data'] is Map<String, dynamic>
              ? jsonData['data'] as Map<String, dynamic>
              : jsonData;
          final leaderboardList = (rawData['leaderboard'] as List<dynamic>)
              .map((entry) => LeaderboardEntry.fromJson(entry as Map<String, dynamic>))
              .toList();

          _leaderboard = leaderboardList;
          _error = null;
        } else {
          _error = jsonData['error'] as String? ?? 'Failed to load leaderboard';
        }
      } else {
        _error = 'Failed to load leaderboard';
      }
    } catch (e) {
      _error = 'Error loading leaderboard: $e';
      DebugLogger.logError('Error loading leaderboard: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Refresh leaderboard
  Future<void> refresh() async {
    await loadLeaderboard();
  }
}
