import 'dart:async';
import 'package:flutter/material.dart';
import '../services/auth_service.dart';
import '../services/session_service.dart';
import '../config/app_config.dart';
import '../l10n/app_localizations.dart';
import '../utils/debug_logger.dart';

/// Widget that shows a warning dialog when session is about to expire.
///
/// This widget checks session expiration time periodically and shows a dialog
/// when the session is within 15 minutes of expiration, allowing the user to
/// extend the session or continue.
class SessionExpirationWarning extends StatefulWidget {
  final Widget child;

  const SessionExpirationWarning({
    super.key,
    required this.child,
  });

  @override
  State<SessionExpirationWarning> createState() => _SessionExpirationWarningState();
}

class _SessionExpirationWarningState extends State<SessionExpirationWarning> {
  final AuthService _authService = AuthService();
  final SessionService _sessionService = SessionService();
  Timer? _checkTimer;
  bool _isDialogShowing = false;

  @override
  void initState() {
    super.initState();
    // Check session expiration every minute for better responsiveness
    // This ensures we catch expiration warnings quickly
    _checkTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      _checkSessionExpiration();
    });
    // Also check immediately after a short delay
    Future.delayed(const Duration(seconds: 10), () {
      _checkSessionExpiration();
    });
  }

  @override
  void dispose() {
    _checkTimer?.cancel();
    super.dispose();
  }

  Future<void> _checkSessionExpiration() async {
    if (_isDialogShowing) return; // Don't show multiple dialogs

    try {
      final lastValidated = await _sessionService.getSessionLastValidated();
      if (lastValidated == null) return;

      final now = DateTime.now();
      final timeSinceLastActivity = now.difference(lastValidated);
      final timeUntilExpiration = AppConfig.sessionTimeout - timeSinceLastActivity;

      // Show warning if within 15 minutes of expiration
      // Use shorter check interval when close to expiration (within 5 minutes)
      if (timeUntilExpiration <= const Duration(minutes: 15) &&
          timeUntilExpiration > Duration.zero) {
        if (mounted && !_isDialogShowing) {
          _isDialogShowing = true;
          _showExpirationWarning(timeUntilExpiration);
        }
      }

      // If very close to expiration (within 5 minutes), check more frequently
      if (timeUntilExpiration <= const Duration(minutes: 5) &&
          timeUntilExpiration > Duration.zero) {
        // Cancel current timer and restart with shorter interval
        _checkTimer?.cancel();
        _checkTimer = Timer.periodic(const Duration(seconds: 30), (_) {
          _checkSessionExpiration();
        });
      }
    } catch (e) {
      DebugLogger.logWarn('AUTH', 'Error checking session expiration: $e');
    }
  }

  void _showExpirationWarning(Duration timeUntilExpiration) {
    final localizations = AppLocalizations.of(context);
    if (localizations == null) return;

    final minutes = timeUntilExpiration.inMinutes;
    final seconds = timeUntilExpiration.inSeconds % 60;

    // Show countdown timer in message
    String message;
    if (minutes > 0) {
      message = 'Your session will expire in $minutes minute${minutes != 1 ? 's' : ''}';
      if (seconds > 0 && minutes < 5) {
        message += ' and $seconds second${seconds != 1 ? 's' : ''}';
      }
      message += '. Would you like to extend it?';
    } else {
      message = 'Your session will expire in $seconds second${seconds != 1 ? 's' : ''}. Would you like to extend it?';
    }

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext dialogContext) {
        final cs = Theme.of(dialogContext).colorScheme;
        return AlertDialog(
          title: Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: cs.tertiary),
              const SizedBox(width: 8),
              const Text('Session Expiring Soon'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(message),
              const SizedBox(height: 16),
              // Show visual countdown indicator
              if (timeUntilExpiration.inMinutes < 5)
                LinearProgressIndicator(
                  value: timeUntilExpiration.inSeconds / (5 * 60),
                  backgroundColor: cs.surfaceContainerHighest,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    timeUntilExpiration.inMinutes < 2 ? cs.error : cs.tertiary,
                  ),
                ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(dialogContext).pop();
                _isDialogShowing = false;
              },
              child: const Text('Continue'),
            ),
            FilledButton(
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                _isDialogShowing = false;
                await _extendSession();
              },
              child: const Text('Extend Session'),
            ),
          ],
        );
      },
    ).then((_) {
      _isDialogShowing = false;
    });
  }

  Future<void> _extendSession() async {
    try {
      DebugLogger.logAuth('User requested to extend session');
      final success = await _authService.refreshSession(forceRefresh: true);
      if (success) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Session extended successfully'),
              duration: Duration(seconds: 2),
            ),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to extend session. Please log in again.'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 3),
            ),
          );
        }
      }
    } catch (e) {
      DebugLogger.logError('Error extending session: $e');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: ${e.toString()}'),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return widget.child;
  }
}
