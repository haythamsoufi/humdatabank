import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'api_service.dart';
import 'auth_error_handler.dart';
import '../utils/debug_logger.dart';
import '../config/app_config.dart';

// Sentry import - make it optional to avoid breaking if package not installed
// ignore: avoid_relative_lib_imports
import 'package:sentry_flutter/sentry_flutter.dart' as sentry;

/// Base class for all app errors
abstract class AppError implements Exception {
  final String message;
  final String? userMessage;
  final String? context;
  final dynamic originalError;
  final StackTrace? stackTrace;

  AppError({
    required this.message,
    this.userMessage,
    this.context,
    this.originalError,
    this.stackTrace,
  });

  /// Get user-friendly error message
  String getUserMessage() {
    return userMessage ?? message;
  }

  /// Get actionable steps for the user
  List<String> getActionableSteps() => [];

  /// Check if error is retryable
  bool get isRetryable => false;

  @override
  String toString() => message;
}

/// Network-related errors (connection issues, timeouts)
class NetworkError extends AppError {
  final bool isTimeout;
  final bool isConnectionError;

  NetworkError({
    required super.message,
    super.userMessage,
    super.context,
    super.originalError,
    super.stackTrace,
    this.isTimeout = false,
    this.isConnectionError = false,
  });

  @override
  String getUserMessage() {
    if (userMessage != null) return userMessage!;

    if (isTimeout) {
      return 'Request timed out. Please check your internet connection and try again.';
    }
    if (isConnectionError) {
      return 'Unable to connect to the server. Please check your internet connection.';
    }
    return 'Network error occurred. Please check your connection and try again.';
  }

  @override
  List<String> getActionableSteps() {
    return [
      'Check your internet connection',
      'Try again in a few moments',
      'If the problem persists, contact support',
    ];
  }

  @override
  bool get isRetryable => true;
}

/// Authentication-related errors (session expired, unauthorized)
class AuthError extends AppError {
  final bool isSessionExpired;
  final bool isUnauthorized;

  AuthError({
    required super.message,
    super.userMessage,
    super.context,
    super.originalError,
    super.stackTrace,
    this.isSessionExpired = false,
    this.isUnauthorized = false,
  });

  @override
  String getUserMessage() {
    if (userMessage != null) return userMessage!;

    if (isSessionExpired) {
      return 'Your session has expired. Please log in again.';
    }
    if (isUnauthorized) {
      return 'You are not authorized to perform this action.';
    }
    return 'Authentication required. Please log in.';
  }

  @override
  List<String> getActionableSteps() {
    return [
      'Log in again to continue',
      'If the problem persists, contact support',
    ];
  }

  @override
  bool get isRetryable => false;
}

/// Validation errors (invalid input, missing fields)
class ValidationError extends AppError {
  final Map<String, String>? fieldErrors;

  ValidationError({
    required super.message,
    super.userMessage,
    super.context,
    super.originalError,
    super.stackTrace,
    this.fieldErrors,
  });

  @override
  String getUserMessage() {
    if (userMessage != null) return userMessage!;
    return 'Please check your input and try again.';
  }

  @override
  List<String> getActionableSteps() {
    final steps = <String>['Review the highlighted fields'];
    if (fieldErrors != null && fieldErrors!.isNotEmpty) {
      steps.addAll(fieldErrors!.values);
    }
    return steps;
  }

  @override
  bool get isRetryable => false;
}

/// Server errors (500, 502, 503, etc.)
class ServerError extends AppError {
  final int? statusCode;
  final String? serverMessage;

  ServerError({
    required super.message,
    super.userMessage,
    super.context,
    super.originalError,
    super.stackTrace,
    this.statusCode,
    this.serverMessage,
  });

  @override
  String getUserMessage() {
    if (userMessage != null) return userMessage!;

    if (statusCode == 503) {
      return 'Service temporarily unavailable. Please try again later.';
    }
    if (statusCode == 502 || statusCode == 504) {
      return 'Server is temporarily unavailable. Please try again in a few moments.';
    }
    if (serverMessage != null && serverMessage!.isNotEmpty) {
      return serverMessage!;
    }
    return 'Server error occurred. Please try again later.';
  }

  @override
  List<String> getActionableSteps() {
    return [
      'Wait a few moments and try again',
      'If the problem persists, contact support',
    ];
  }

  @override
  bool get isRetryable =>
      statusCode == 503 || statusCode == 502 || statusCode == 504;
}

/// Unknown or unexpected errors
class UnknownError extends AppError {
  UnknownError({
    required super.message,
    super.userMessage,
    super.context,
    super.originalError,
    super.stackTrace,
  });

  @override
  String getUserMessage() {
    return userMessage ?? 'An unexpected error occurred. Please try again.';
  }

  @override
  List<String> getActionableSteps() {
    return [
      'Try again',
      'If the problem persists, contact support',
    ];
  }

  @override
  bool get isRetryable => true;
}

/// Centralized error handler service
class ErrorHandler {
  static final ErrorHandler _instance = ErrorHandler._internal();
  factory ErrorHandler() => _instance;
  ErrorHandler._internal();

  final AuthErrorHandler _authErrorHandler = AuthErrorHandler();

  /// Parse an exception into an AppError
  AppError parseError({
    required dynamic error,
    StackTrace? stackTrace,
    String? context,
    http.Response? response,
  }) {
    // Handle AuthenticationException
    if (error is AuthenticationException) {
      return AuthError(
        message: error.message,
        context: context,
        originalError: error,
        stackTrace: stackTrace,
        isSessionExpired: error.message.toLowerCase().contains('expired'),
        isUnauthorized: true,
      );
    }

    // Handle HTTP response errors
    if (response != null) {
      return _parseHttpResponse(response,
          context: context, originalError: error, stackTrace: stackTrace);
    }

    // Handle timeout errors
    if (error is TimeoutException) {
      return NetworkError(
        message: 'Request timed out: ${error.toString()}',
        context: context,
        originalError: error,
        stackTrace: stackTrace,
        isTimeout: true,
      );
    }

    // Handle network/connection errors
    final errorStr = error.toString().toLowerCase();
    if (errorStr.contains('socketexception') ||
        errorStr.contains('connection') ||
        errorStr.contains('network') ||
        errorStr.contains('failed host lookup')) {
      return NetworkError(
        message: error.toString(),
        context: context,
        originalError: error,
        stackTrace: stackTrace,
        isConnectionError: true,
      );
    }

    // Handle authentication errors by string matching
    if (_authErrorHandler.isAuthenticationError(error)) {
      return AuthError(
        message: error.toString(),
        context: context,
        originalError: error,
        stackTrace: stackTrace,
        isSessionExpired:
            errorStr.contains('expired') || errorStr.contains('session'),
        isUnauthorized: true,
      );
    }

    // Default to unknown error
    return UnknownError(
      message: error.toString(),
      context: context,
      originalError: error,
      stackTrace: stackTrace,
    );
  }

  /// Parse HTTP response into appropriate error type
  AppError _parseHttpResponse(
    http.Response response, {
    String? context,
    dynamic originalError,
    StackTrace? stackTrace,
  }) {
    final statusCode = response.statusCode;
    String? serverMessage;

    // Try to extract error message from response body
    try {
      final body = response.body;
      if (body.isNotEmpty) {
        // Try JSON first
        try {
          final json = jsonDecode(body);
          serverMessage = json['error'] ?? json['message'] ?? json['detail'];
        } catch (_) {
          // Not JSON, try to extract from HTML or plain text
          if (body.length < 500) {
            serverMessage = body;
          }
        }
      }
    } catch (_) {
      // Ignore parsing errors
    }

    // Categorize by status code
    if (statusCode == 401 || statusCode == 403) {
      return AuthError(
        message: 'HTTP $statusCode: ${response.reasonPhrase ?? 'Unauthorized'}',
        userMessage: statusCode == 401
            ? 'Your session has expired. Please log in again.'
            : 'You are not authorized to perform this action.',
        context: context,
        originalError: originalError,
        stackTrace: stackTrace,
        isSessionExpired: statusCode == 401,
        isUnauthorized: true,
      );
    }

    if (statusCode == 400 || statusCode == 422) {
      // Try to parse validation errors
      Map<String, String>? fieldErrors;
      try {
        final json = jsonDecode(response.body);
        if (json is Map && json.containsKey('errors')) {
          fieldErrors = Map<String, String>.from(json['errors']);
        }
      } catch (_) {
        // Ignore parsing errors
      }

      return ValidationError(
        message: 'HTTP $statusCode: ${response.reasonPhrase ?? 'Bad Request'}',
        userMessage: serverMessage ?? 'Please check your input and try again.',
        context: context,
        originalError: originalError,
        stackTrace: stackTrace,
        fieldErrors: fieldErrors,
      );
    }

    if (statusCode >= 500) {
      return ServerError(
        message: 'HTTP $statusCode: ${response.reasonPhrase ?? 'Server Error'}',
        userMessage: serverMessage,
        context: context,
        originalError: originalError,
        stackTrace: stackTrace,
        statusCode: statusCode,
        serverMessage: serverMessage,
      );
    }

    // Default to unknown error for other status codes
    return UnknownError(
      message: 'HTTP $statusCode: ${response.reasonPhrase ?? 'Unknown Error'}',
      userMessage: serverMessage ?? 'An error occurred. Please try again.',
      context: context,
      originalError: originalError,
      stackTrace: stackTrace,
    );
  }

  /// Execute an API call with automatic error handling and retry
  Future<T?> executeWithErrorHandling<T>({
    required Future<T> Function() apiCall,
    String? context,
    T? defaultValue,
    int maxRetries = 0,
    Duration retryDelay = const Duration(seconds: 2),
    bool handleAuthErrors = true,
  }) async {
    int attempts = 0;

    while (attempts <= maxRetries) {
      try {
        return await apiCall();
      } on AuthenticationException catch (e, stackTrace) {
        final error = parseError(
          error: e,
          stackTrace: stackTrace,
          context: context,
        );

        if (handleAuthErrors && error is AuthError) {
          await _authErrorHandler.handleAuthenticationError(
            context: context,
            silent: false,
          );
        }

        DebugLogger.logError(
            '${context ?? "API"} error: ${error.getUserMessage()}');
        return defaultValue;
      } catch (e, stackTrace) {
        final error = parseError(
          error: e,
          stackTrace: stackTrace,
          context: context,
        );

        // Handle authentication errors
        if (handleAuthErrors && error is AuthError) {
          await _authErrorHandler.handleAuthenticationError(
            context: context,
            silent: false,
          );
          DebugLogger.logError(
              '${context ?? "API"} auth error: ${error.getUserMessage()}');
          return defaultValue;
        }

        // Check if retryable and we have retries left
        if (error.isRetryable && attempts < maxRetries) {
          attempts++;
          DebugLogger.logError(
              '${context ?? "API"} error (attempt $attempts/${maxRetries + 1}): ${error.getUserMessage()}. Retrying...');
          await Future.delayed(retryDelay);
          continue;
        }

        // Log error
        DebugLogger.logError(
            '${context ?? "API"} error: ${error.getUserMessage()}');
        DebugLogger.logError('Error details: ${error.message}');
        if (error.stackTrace != null) {
          DebugLogger.logError('Stack trace: ${error.stackTrace}');
        }

        return defaultValue;
      }
    }

    return defaultValue;
  }

  /// Log error for reporting (can be extended to send to Sentry/Crashlytics)
  void logError(AppError error) {
    DebugLogger.logError(
        'Error in ${error.context ?? "unknown context"}: ${error.message}');
    if (error.stackTrace != null) {
      DebugLogger.logError('Stack trace: ${error.stackTrace}');
    }

    // Send to Sentry if configured
    _sendToSentry(error);
  }

  /// Send error to Sentry if configured
  void _sendToSentry(AppError error) async {
    // Only send to Sentry if DSN is configured
    if (AppConfig.sentryDsn.isEmpty) {
      return;
    }

    try {
      // Set tags and extra context before capturing
      sentry.Sentry.configureScope((scope) {
        // Set tags
        scope.setTag('error_type', error.runtimeType.toString());
        scope.setTag('error_retryable', error.isRetryable.toString());
        scope.setTag('context', error.context ?? 'unknown');

        // Add additional context based on error type
        if (error is NetworkError) {
          scope.setTag('is_timeout', error.isTimeout.toString());
          scope.setTag('is_connection_error', error.isConnectionError.toString());
        } else if (error is AuthError) {
          scope.setTag('is_session_expired', error.isSessionExpired.toString());
          scope.setTag('is_unauthorized', error.isUnauthorized.toString());
        } else if (error is ServerError) {
          scope.setTag('status_code', error.statusCode?.toString() ?? 'unknown');
          if (error.serverMessage != null) {
            scope.setExtra('server_message', error.serverMessage);
          }
        } else if (error is ValidationError) {
          if (error.fieldErrors != null) {
            scope.setExtra('field_errors', error.fieldErrors);
          }
        }

        // Set extra context
        scope.setExtra('user_message', error.getUserMessage());
        scope.setExtra('actionable_steps', error.getActionableSteps().join(', '));
        if (error.context != null) {
          scope.setExtra('context', error.context!);
        }
      });

      // Use captureException - simpler API
      await sentry.Sentry.captureException(
        error.originalError ?? error,
        stackTrace: error.stackTrace,
      );
    } catch (e) {
      // Sentry not initialized or capture failed - ignore silently
      // This allows the app to work even if Sentry is not properly configured
      DebugLogger.logWarn('ERROR_HANDLER', 'Failed to send error to Sentry: $e');
    }
  }


  /// Set user context for Sentry (call when user logs in)
  static void setUserContext({
    required String userId,
    String? email,
    String? username,
    Map<String, String>? additionalData,
  }) {
    if (AppConfig.sentryDsn.isEmpty) {
      return;
    }

    try {
      sentry.Sentry.configureScope((scope) {
        // Convert Map<String, String> to Map<String, dynamic>
        Map<String, dynamic>? dataMap;
        if (additionalData != null && additionalData.isNotEmpty) {
          dataMap = {};
          additionalData.forEach((key, value) {
            dataMap![key] = value;
          });
        }

        scope.setUser(sentry.SentryUser(
          id: userId,
          email: email,
          username: username,
          data: dataMap,
        ));
      });
      DebugLogger.logInfo('ERROR_HANDLER', 'Sentry user context set: $userId');
    } catch (e) {
      DebugLogger.logWarn('ERROR_HANDLER', 'Failed to set Sentry user context: $e');
    }
  }

  /// Clear user context for Sentry (call when user logs out)
  static void clearUserContext() {
    if (AppConfig.sentryDsn.isEmpty) {
      return;
    }

    try {
      sentry.Sentry.configureScope((scope) {
        scope.setUser(null);
      });
      DebugLogger.logInfo('ERROR_HANDLER', 'Sentry user context cleared');
    } catch (e) {
      DebugLogger.logWarn('ERROR_HANDLER', 'Failed to clear Sentry user context: $e');
    }
  }

  /// Add breadcrumb for Sentry (useful for tracking user actions)
  static void addBreadcrumb({
    required String message,
    String? category,
    sentry.SentryLevel level = sentry.SentryLevel.info,
    Map<String, dynamic>? data,
  }) {
    if (AppConfig.sentryDsn.isEmpty) {
      return;
    }

    try {
      sentry.Sentry.addBreadcrumb(
        sentry.Breadcrumb(
          message: message,
          category: category,
          level: level,
          data: data,
          timestamp: DateTime.now(),
        ),
      );
    } catch (e) {
      DebugLogger.logWarn('ERROR_HANDLER', 'Failed to add Sentry breadcrumb: $e');
    }
  }
}
