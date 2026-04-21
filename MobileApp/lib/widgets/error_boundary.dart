import 'package:flutter/material.dart';
import '../services/error_handler.dart';
import 'error_state.dart';

/// Error boundary widget that catches errors and displays them gracefully
class ErrorBoundary extends StatefulWidget {
  final Widget child;
  final Widget Function(BuildContext context, AppError error)? errorBuilder;
  final String? context;

  const ErrorBoundary({
    super.key,
    required this.child,
    this.errorBuilder,
    this.context,
  });

  @override
  State<ErrorBoundary> createState() => _ErrorBoundaryState();
}

class _ErrorBoundaryState extends State<ErrorBoundary> {
  AppError? _error;

  @override
  void initState() {
    super.initState();
    // Catch Flutter framework errors
    FlutterError.onError = (FlutterErrorDetails details) {
      final error = ErrorHandler().parseError(
        error: details.exception,
        stackTrace: details.stack,
        context: widget.context ?? 'ErrorBoundary',
      );
      _handleError(error);
    };
  }

  void _handleError(AppError error) {
    if (mounted) {
      setState(() {
        _error = error;
      });
      ErrorHandler().logError(error);
    }
  }

  void _clearError() {
    if (mounted) {
      setState(() {
        _error = null;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      if (widget.errorBuilder != null) {
        return widget.errorBuilder!(context, _error!);
      }
      return _defaultErrorWidget(_error!);
    }

    return widget.child;
  }

  Widget _defaultErrorWidget(AppError error) {
    return Scaffold(
      body: AppErrorState(
        message: error.getUserMessage(),
        onRetry: error.isRetryable ? _clearError : null,
      ),
    );
  }
}

/// Wrapper for async operations with error handling
class AsyncErrorHandler {
  static Future<T?> execute<T>({
    required Future<T> Function() operation,
    required Function(AppError) onError,
    String? context,
    T? defaultValue,
  }) async {
    try {
      return await operation();
    } catch (e, stackTrace) {
      final error = ErrorHandler().parseError(
        error: e,
        stackTrace: stackTrace,
        context: context,
      );
      ErrorHandler().logError(error);
      onError(error);
      return defaultValue;
    }
  }
}
