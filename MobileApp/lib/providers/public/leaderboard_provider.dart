import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';

/// Leaderboard entry model
class LeaderboardEntry {
  final int rank;
  final int userId;
  final String name;
  final String email;
  final int score;

  LeaderboardEntry({
    required this.rank,
    required this.userId,
    required this.name,
    required this.email,
    required this.score,
  });

  factory LeaderboardEntry.fromJson(Map<String, dynamic> json) {
    return LeaderboardEntry(
      rank: json['rank'] as int,
      userId: json['user_id'] as int,
      name: json['name'] as String,
      email: json['email'] as String,
      score: json['score'] as int,
    );
  }
}

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
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final response = await _apiService.get(
        '/api/v1/quiz/leaderboard',
        queryParams: {'limit': limit.toString()},
        includeAuth: false, // Public endpoint
      );

      if (response.statusCode == 200) {
        final data = response.body;
        final jsonData = jsonDecode(data) as Map<String, dynamic>;

        if (jsonData['success'] == true) {
          final leaderboardList = (jsonData['leaderboard'] as List<dynamic>)
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
