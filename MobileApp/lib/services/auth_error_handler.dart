import 'package:flutter/foundation.dart';
import 'auth_service.dart';
import 'api_service.dart';
import '../providers/shared/auth_provider.dart';
import '../utils/debug_logger.dart';

/// Centralized service for handling authentication errors across the app.
/// This ensures consistent behavior when sessions expire or become invalid.
class AuthErrorHandler {
  static final AuthErrorHandler _instance = AuthErrorHandler._internal();
  factory AuthErrorHandler() => _instance;
  AuthErrorHandler._internal();

  AuthProvider? _authProvider;
  final AuthService _authService = AuthService();

  /// Set the auth provider reference (called from main app initialization)
  void setAuthProvider(AuthProvider authProvider) {
    _authProvider = authProvider;
  }

  /// Handle authentication errors consistently across the app.
  /// This clears the session and notifies the auth provider.
  Future<void> handleAuthenticationError({
    String? context,
    bool silent = false,
  }) async {
    final contextStr = context != null ? '[$context] ' : '';
    if (!silent) {
      DebugLogger.logApi(
          '${contextStr}Authentication error detected - clearing session');
    }

    // Clear session via auth provider if available
    if (_authProvider != null) {
      await _authProvider!.handleAuthenticationError();
    } else {
      // Fallback: clear session directly
      await _authService.logout();
    }
  }

  /// Wrapper for API calls that automatically handles authentication errors.
  /// Use this for API calls that require authentication.
  ///
  /// Example:
  /// ```dart
  /// final result = await AuthErrorHandler().executeWithAuthHandling(
  ///   () => _api.get('/endpoint'),
  ///   context: 'Dashboard',
  /// );
  /// ```
  Future<T?> executeWithAuthHandling<T>({
    required Future<T> Function() apiCall,
    String? context,
    T? defaultValue,
    bool silent = false,
  }) async {
    try {
      return await apiCall();
    } on AuthenticationException catch (e) {
      await handleAuthenticationError(context: context, silent: silent);
      return defaultValue;
    } catch (e) {
      // Check if it's an authentication error in the error message
      if (isAuthenticationError(e)) {
        await handleAuthenticationError(context: context, silent: silent);
        return defaultValue;
      }
      rethrow;
    }
  }

  /// Check if an error is an authentication error.
  bool isAuthenticationError(dynamic error) {
    if (error is AuthenticationException) {
      return true;
    }

    final errorStr = error.toString().toLowerCase();
    return errorStr.contains('401') ||
        errorStr.contains('403') ||
        errorStr.contains('authentication') ||
        errorStr.contains('session expired') ||
        errorStr.contains('unauthorized') ||
        errorStr.contains('login') ||
        errorStr.contains('credential');
  }

  /// Get user-friendly error message from error.
  String getUserFriendlyErrorMessage(dynamic error) {
    if (error is AuthenticationException) {
      return error.message;
    }

    final errorStr = error.toString().toLowerCase();

    // Network errors
    if (errorStr.contains('timeout') || errorStr.contains('timed out')) {
      return 'Request timed out. Please check your internet connection and try again.';
    }
    if (errorStr.contains('network') || errorStr.contains('connection') || errorStr.contains('socket')) {
      return 'Network error. Please check your internet connection and try again.';
    }

    // Authentication errors
    if (errorStr.contains('401') || errorStr.contains('unauthorized')) {
      return 'Your session has expired. Please log in again.';
    }
    if (errorStr.contains('403') || errorStr.contains('forbidden')) {
      return 'You do not have permission to perform this action.';
    }
    if (errorStr.contains('session expired')) {
      return 'Your session has expired. Please log in again.';
    }
    if (errorStr.contains('invalid') && errorStr.contains('credential')) {
      return 'Invalid email or password. Please try again.';
    }

    // Server errors
    if (errorStr.contains('500') || errorStr.contains('internal server error')) {
      return 'Server error. Please try again later or contact support.';
    }
    if (errorStr.contains('502') || errorStr.contains('bad gateway')) {
      return 'Service temporarily unavailable. Please try again later.';
    }
    if (errorStr.contains('503') || errorStr.contains('service unavailable')) {
      return 'Service temporarily unavailable. Please try again later.';
    }

    // Default
    return 'An error occurred. Please try again.';
  }

  /// Handle HTTP response status codes that indicate authentication errors.
  Future<void> handleHttpResponse({
    required int statusCode,
    String? context,
    bool silent = false,
  }) async {
    if (statusCode == 401 || statusCode == 403) {
      await handleAuthenticationError(context: context, silent: silent);
    }
  }
}
