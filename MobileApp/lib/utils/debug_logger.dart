import 'package:flutter/foundation.dart'
    show kDebugMode, kReleaseMode, kProfileMode;

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

  // Minimum log level (only logs at or above this level)
  static LogLevel _minLevel = LogLevel.debug;

  /// Set minimum log level (only logs at or above this level)
  static void setMinLevel(LogLevel level) {
    _minLevel = level;
  }

  /// Log a message with a tag and level
  static void log(String tag, String message,
      {LogLevel level = LogLevel.debug}) {
    if (!enabled) return;
    if (level.index < _minLevel.index) return;

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
      masked =
          '${masked.substring(0, 200)}... [TRUNCATED ${masked.length - 200} chars]';
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
