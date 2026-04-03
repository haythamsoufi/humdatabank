import 'package:flutter/material.dart';
import '../services/error_handler.dart';
import '../utils/debug_logger.dart';

/// Error boundary widget that catches errors and displays them gracefully
class ErrorBoundary extends StatefulWidget {
  final Widget child;
  final Widget Function(BuildContext context, AppError error)? errorBuilder;
  final String? context;

  const ErrorBoundary({
    Key? key,
    required this.child,
    this.errorBuilder,
    this.context,
  }) : super(key: key);

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
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                Icons.error_outline,
                size: 64,
                color: Colors.red.shade300,
              ),
              const SizedBox(height: 16),
              Text(
                'Something went wrong',
                style: Theme.of(context).textTheme.headlineSmall,
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                error.getUserMessage(),
                style: Theme.of(context).textTheme.bodyMedium,
                textAlign: TextAlign.center,
              ),
              if (error.getActionableSteps().isNotEmpty) ...[
                const SizedBox(height: 24),
                ...error.getActionableSteps().map((step) => Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4.0),
                      child: Row(
                        children: [
                          Icon(
                            Icons.check_circle_outline,
                            size: 16,
                            color: Colors.grey.shade600,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              step,
                              style: Theme.of(context).textTheme.bodySmall,
                            ),
                          ),
                        ],
                      ),
                    )),
              ],
              const SizedBox(height: 24),
              if (error.isRetryable)
                ElevatedButton.icon(
                  onPressed: _clearError,
                  icon: const Icon(Icons.refresh),
                  label: const Text('Try Again'),
                ),
            ],
          ),
        ),
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
