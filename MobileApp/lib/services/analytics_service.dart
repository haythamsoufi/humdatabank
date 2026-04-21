import 'package:firebase_analytics/firebase_analytics.dart';
import '../utils/debug_logger.dart';

class AnalyticsService {
  static final AnalyticsService _instance = AnalyticsService._internal();
  factory AnalyticsService() => _instance;
  AnalyticsService._internal();

  late FirebaseAnalytics _analytics;
  bool _initialized = false;

  FirebaseAnalyticsObserver? _observer;

  Future<void> initialize() async {
    if (_initialized) return;
    try {
      _analytics = FirebaseAnalytics.instance;
      _observer = FirebaseAnalyticsObserver(analytics: _analytics);
      _initialized = true;
      DebugLogger.logInfo('ANALYTICS', 'Firebase Analytics initialized');
    } catch (e) {
      DebugLogger.logError('Failed to initialize Firebase Analytics: $e');
    }
  }

  FirebaseAnalyticsObserver? get observer => _observer;

  Future<void> logScreenView({required String screenName, String? screenClass}) async {
    if (!_initialized) return;
    try {
      await _analytics.logScreenView(
        screenName: screenName,
        screenClass: screenClass,
      );
    } catch (e) {
      DebugLogger.logError('Failed to log screen view: $e');
    }
  }

  Future<void> logLogin({String? method}) async {
    if (!_initialized) return;
    try {
      await _analytics.logLogin(loginMethod: method);
    } catch (e) {
      DebugLogger.logError('Failed to log login event: $e');
    }
  }

  Future<void> logEvent({required String name, Map<String, Object>? parameters}) async {
    if (!_initialized) return;
    try {
      await _analytics.logEvent(name: name, parameters: parameters);
    } catch (e) {
      DebugLogger.logError('Failed to log event $name: $e');
    }
  }

  Future<void> setUserId(String? userId) async {
    if (!_initialized) return;
    try {
      await _analytics.setUserId(id: userId);
    } catch (e) {
      DebugLogger.logError('Failed to set user ID: $e');
    }
  }

  Future<void> setUserProperty({required String name, required String? value}) async {
    if (!_initialized) return;
    try {
      await _analytics.setUserProperty(name: name, value: value);
    } catch (e) {
      DebugLogger.logError('Failed to set user property: $e');
    }
  }

  Future<void> logFormStart({required String formName}) async {
    await logEvent(name: 'form_start', parameters: {'form_name': formName});
  }

  Future<void> logFormComplete({required String formName}) async {
    await logEvent(name: 'form_complete', parameters: {'form_name': formName});
  }

  Future<void> logAiChatStart() async {
    await logEvent(name: 'ai_chat_start');
  }

  Future<void> logAiChatMessage({required String role}) async {
    await logEvent(name: 'ai_chat_message', parameters: {'role': role});
  }

  Future<void> logOfflineSync({required bool success, int? itemCount}) async {
    await logEvent(
      name: 'offline_sync',
      parameters: {
        'success': success.toString(),
        'item_count': ?itemCount,
      },
    );
  }

  Future<void> logIndicatorView({required int indicatorId, required String indicatorName}) async {
    await logEvent(
      name: 'indicator_view',
      parameters: {
        'indicator_id': indicatorId,
        'indicator_name': indicatorName,
      },
    );
  }

  Future<void> logQuizComplete({required int score, required int totalQuestions}) async {
    await logEvent(
      name: 'quiz_complete',
      parameters: {
        'score': score,
        'total_questions': totalQuestions,
      },
    );
  }

  Future<void> logLanguageChange({required String language}) async {
    await logEvent(name: 'language_change', parameters: {'language': language});
    await setUserProperty(name: 'preferred_language', value: language);
  }

  Future<void> logSearch({required String searchTerm}) async {
    if (!_initialized) return;
    try {
      await _analytics.logSearch(searchTerm: searchTerm);
    } catch (e) {
      DebugLogger.logError('Failed to log search: $e');
    }
  }
}
