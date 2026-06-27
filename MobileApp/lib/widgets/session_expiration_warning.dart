import 'dart:async';
import 'package:flutter/material.dart';
import '../di/service_locator.dart';
import '../services/auth_service.dart';
import '../services/jwt_token_service.dart';
import '../l10n/app_localizations.dart';
import '../utils/debug_logger.dart';

/// Warns when the JWT access token is close to expiry and offers a one-tap
/// refresh via the mobile refresh endpoint.
class SessionExpirationWarning extends StatefulWidget {
  final Widget child;

  const SessionExpirationWarning({
    super.key,
    required this.child,
  });

  @override
  State<SessionExpirationWarning> createState() =>
      _SessionExpirationWarningState();
}

class _SessionExpirationWarningState extends State<SessionExpirationWarning> {
  late final AuthService _authService = sl<AuthService>();
  late final JwtTokenService _jwtService = sl<JwtTokenService>();
  Timer? _checkTimer;
  bool _isDialogShowing = false;

  static const Duration _warningThreshold = Duration(minutes: 15);

  @override
  void initState() {
    super.initState();
    _checkTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      _checkAccessTokenExpiration();
    });
    Future.delayed(const Duration(seconds: 10), _checkAccessTokenExpiration);
  }

  @override
  void dispose() {
    _checkTimer?.cancel();
    super.dispose();
  }

  Future<void> _checkAccessTokenExpiration() async {
    if (_isDialogShowing) return;

    try {
      final hasRefresh = await _jwtService.hasRefreshToken();
      if (!hasRefresh) return;

      final timeUntilExpiry = await _jwtService.timeUntilAccessExpiry();
      if (timeUntilExpiry == null) return;

      if (timeUntilExpiry <= _warningThreshold) {
        if (mounted && !_isDialogShowing) {
          _isDialogShowing = true;
          _showExpirationWarning(
            timeUntilExpiry <= Duration.zero
                ? _warningThreshold
                : timeUntilExpiry,
          );
        }
      }

      if (timeUntilExpiry <= const Duration(minutes: 5) &&
          timeUntilExpiry > Duration.zero) {
        _checkTimer?.cancel();
        _checkTimer = Timer.periodic(const Duration(seconds: 30), (_) {
          _checkAccessTokenExpiration();
        });
      }
    } catch (e) {
      DebugLogger.logWarn('AUTH', 'Error checking JWT expiry: $e');
    }
  }

  void _showExpirationWarning(Duration timeUntilExpiration) {
    final localizations = AppLocalizations.of(context);
    if (localizations == null) return;

    final minutes = timeUntilExpiration.inMinutes;
    final seconds = timeUntilExpiration.inSeconds % 60;

    String message;
    if (minutes > 0) {
      message =
          'Your sign-in will expire in $minutes minute${minutes != 1 ? 's' : ''}';
      if (seconds > 0 && minutes < 5) {
        message += ' and $seconds second${seconds != 1 ? 's' : ''}';
      }
      message += '. Would you like to refresh it now?';
    } else {
      message =
          'Your sign-in has expired or is about to expire. Refresh now to stay signed in?';
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
              const Text('Sign-in Expiring Soon'),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(message),
              const SizedBox(height: 16),
              if (timeUntilExpiration.inMinutes < 5)
                LinearProgressIndicator(
                  value: timeUntilExpiration.inSeconds / (5 * 60),
                  backgroundColor: cs.surfaceContainerHighest,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    timeUntilExpiration.inMinutes < 2
                        ? cs.error
                        : cs.tertiary,
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
              child: const Text('Refresh Sign-in'),
            ),
          ],
        );
      },
    ).then((_) {
      _isDialogShowing = false;
    });
  }

  void _resetToNormalCheckInterval() {
    _checkTimer?.cancel();
    _checkTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      _checkAccessTokenExpiration();
    });
  }

  Future<void> _extendSession() async {
    try {
      DebugLogger.logAuth('User requested JWT refresh from expiry warning');
      final success = await _authService.refreshSession(forceRefresh: true);
      if (success) {
        _resetToNormalCheckInterval();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Sign-in refreshed successfully'),
              duration: Duration(seconds: 2),
            ),
          );
        }
      } else {
        await _authService.invalidateLocalAuth(
          reason: 'Refresh rejected from expiry warning',
        );
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Failed to refresh sign-in. Please log in again.'),
              backgroundColor: Colors.red,
              duration: Duration(seconds: 3),
            ),
          );
        }
      }
    } catch (e) {
      DebugLogger.logError('Error refreshing JWT from expiry warning: $e');
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
