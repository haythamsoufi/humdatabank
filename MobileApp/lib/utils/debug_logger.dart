import 'package:flutter/foundation.dart'
    show kDebugMode, kProfileMode;

// Android logcat lines such as:
//   I/VRI[MainActivity]@…: call setFrameRateCategory …
// come from the OS (ViewRootImpl), not from [DebugLogger]. They cannot be
// disabled from Dart. Hide them in the device log UI, e.g. Android Studio /
// Logcat query: `-tag:VRI` (exclude tag containing VRI), or `adb logcat` with
// an equivalent filter.

/// Log levels for filtering
enum LogLevel {
  debug,
  info,
  warn,
  error,
}

/// Centralized logging utility with log levels and sensitive data masking
/// Automatically disabled in release builds for security and performance
class DebugLogger {
  // Automatically disable in release builds
  static bool get enabled => kDebugMode || kProfileMode;

  /// True when verbose DEBUG logging is enabled (`VERBOSE_LOGS` via define or `.env`).
  static bool verboseDebugLogs = false;

  // Minimum log level (only logs at or above this level)
  static LogLevel _minLevel = LogLevel.info;

  /// Minimum log level (only logs at or above this level)
  static set minLevel(LogLevel level) => _minLevel = level;

  /// Call from [main] after `.env` is loaded. Default is quiet: [LogLevel.info] only.
  /// Enable full DEBUG (API/NAV/ORGS spam) with `--dart-define=VERBOSE_LOGS=true`
  /// or `VERBOSE_LOGS=true` in `.env`.
  static void applyStartupLogPolicy({bool? envVerboseLogs}) {
    const fromDefine = bool.fromEnvironment('VERBOSE_LOGS', defaultValue: false);
    verboseDebugLogs = fromDefine || (envVerboseLogs == true);
    _minLevel = verboseDebugLogs ? LogLevel.debug : LogLevel.info;
  }

  /// When non-null, only tags in this set are printed.
  /// Use [focusOnTags] / [unfocusTags] to control during investigations.
  static Set<String>? _allowedTags;

  /// Restrict output to [tags] only — silences every other tag.
  /// Call [unfocusTags] to restore normal behaviour.
  static void focusOnTags(Set<String> tags) => _allowedTags = Set.unmodifiable(tags);

  /// Remove tag restriction and restore normal logging.
  static void unfocusTags() => _allowedTags = null;

  /// Log a message with a tag and level
  static void log(String tag, String message,
      {LogLevel level = LogLevel.debug}) {
    if (!enabled) return;
    if (level.index < _minLevel.index) return;
    final allowed = _allowedTags;
    if (allowed != null && !allowed.contains(tag)) return;

    // Mask sensitive data before logging
    final safeMessage = _maskSensitiveData(message);

    final levelPrefix = _getLevelPrefix(level);
    print('[$levelPrefix][$tag] $safeMessage');
  }

  /// Get level prefix for log output
  static String _getLevelPrefix(LogLevel level) {
    switch (level) {
      case LogLevel.debug:
        return 'DEBUG';
      case LogLevel.info:
        return 'INFO';
      case LogLevel.warn:
        return 'WARN';
      case LogLevel.error:
        return 'ERROR';
    }
  }

  /// Mask sensitive data in log messages
  static String _maskSensitiveData(String message) {
    String masked = message;

    // Mask passwords (password=value, password: value, etc.)
    masked = masked.replaceAllMapped(
      RegExp(r'(password\s*[:=]\s*)([^\s&"<>]+)', caseSensitive: false),
      (match) => '${match.group(1)}***MASKED***',
    );

    // Mask session cookies (session=value)
    masked = masked.replaceAllMapped(
      RegExp(r'(session\s*=\s*)([^;,\s]+)', caseSensitive: false),
      (match) => '${match.group(1)}***MASKED***',
    );

    // Mask HTTP Authorization Bearer tokens (logged in header dumps)
    masked = masked.replaceAllMapped(
      RegExp(
        r'(Authorization\s*:\s*Bearer\s+)(\S+)',
        caseSensitive: false,
      ),
      (match) => '${match.group(1)}***MASKED***',
    );

    // Mask tokens (token=value, token: value, etc.)
    masked = masked.replaceAllMapped(
      RegExp(r'(token\s*[:=]\s*)([^\s&"<>]+)', caseSensitive: false),
      (match) => '${match.group(1)}***MASKED***',
    );

    // Mask API keys (api_key=value, api-key: value, etc.)
    masked = masked.replaceAllMapped(
      RegExp(r'(api[_-]?key\s*[:=]\s*)([^\s&"<>]+)', caseSensitive: false),
      (match) => '${match.group(1)}***MASKED***',
    );

    // Mask email addresses (but keep domain visible for debugging)
    masked = masked.replaceAllMapped(
      RegExp(r'\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'),
      (match) => '***@${match.group(2)}',
    );

    // Mask long strings that might be sensitive (over 200 chars)
    // This helps prevent accidental logging of large data structures
    if (masked.length > 500) {
      const cap = 200;
      final take = masked.length < cap ? masked.length : cap;
      masked =
          '${masked.substring(0, take)}... [TRUNCATED ${masked.length - take} chars]';
    }

    return masked;
  }

  // Convenience methods with appropriate log levels
  static void logApi(String message, {LogLevel level = LogLevel.debug}) =>
      log('API', message, level: level);

  static void logAuth(String message, {LogLevel level = LogLevel.info}) =>
      log('AUTH', message, level: level);

  static void logDashboard(String message, {LogLevel level = LogLevel.debug}) =>
      log('DASHBOARD', message, level: level);

  static void logNotifications(String message,
          {LogLevel level = LogLevel.debug}) =>
      log('NOTIFICATIONS', message, level: level);

  static void logWebView(String message, {LogLevel level = LogLevel.debug}) =>
      log('WEBVIEW', message, level: level);

  static void logNav(String message, {LogLevel level = LogLevel.debug}) =>
      log('NAV', message, level: level);

  static void logError(String message) =>
      log('ERROR', message, level: LogLevel.error);

  // Info level logging
  static void logInfo(String tag, String message) =>
      log(tag, message, level: LogLevel.info);

  // Warning level logging
  static void logWarn(String tag, String message) =>
      log(tag, message, level: LogLevel.warn);

  // Error level logging
  static void logErrorWithTag(String tag, String message) =>
      log(tag, message, level: LogLevel.error);
}
