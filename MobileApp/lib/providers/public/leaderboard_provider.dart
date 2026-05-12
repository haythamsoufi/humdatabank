import 'package:flutter/foundation.dart';
import '../../models/public/leaderboard_entry.dart';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

/// Leaderboard provider that manages leaderboard data
class LeaderboardProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _apiService = sl<ApiService>();

  List<LeaderboardEntry> _leaderboard = [];

  List<LeaderboardEntry> get leaderboard => _leaderboard;
  bool get isLoading => opLoading;
  String? get error => opError;

  /// Load leaderboard from backend
  Future<void> loadLeaderboard({int limit = 5}) async {
    if (shouldDeferRemoteFetch) {
      notifyListeners();
      return;
    }
    await runAsyncOperation(() async {
      final response = await _apiService.get(
        AppConfig.mobileQuizLeaderboardEndpoint,
        queryParams: {'limit': limit.toString()},
        // Matches Backoffice: GET /data/quiz/leaderboard uses @mobile_auth_required
        // (same module as submit-score; scores are attributed to users).
        includeAuth: true,
      );

      if (response.statusCode == 200) {
        final jsonData = decodeJsonObject(response.body);

        if (jsonData['success'] == true) {
          final rawData = mobileNestedDataOrRootMap(jsonData);
          final list = rawData['leaderboard'] as List<dynamic>?;
          if (list == null) {
            opError = 'Failed to load leaderboard';
            return;
          }
          _leaderboard = list
              .map((entry) =>
                  LeaderboardEntry.fromJson(entry as Map<String, dynamic>))
              .toList();
          opError = null;
        } else {
          opError =
              jsonData['error'] as String? ?? 'Failed to load leaderboard';
        }
      } else {
        opError = 'Failed to load leaderboard';
      }
    });
  }

  /// Refresh leaderboard
  Future<void> refresh() async {
    await loadLeaderboard();
  }
}
