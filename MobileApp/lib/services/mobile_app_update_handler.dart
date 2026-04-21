import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart'
    show defaultTargetPlatform, kIsWeb, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

import '../config/app_config.dart';
import '../config/app_navigation.dart';
import '../utils/app_spacing.dart';
import '../utils/debug_logger.dart';

/// Shows a blocking dialog when the backoffice rejects the app version (HTTP 426 /
/// `error_code: APP_UPDATE_REQUIRED`). Registered from [DioClient] and [ApiService]
/// so all transports surface the same message.
class MobileAppUpdateHandler {
  MobileAppUpdateHandler._();
  static final MobileAppUpdateHandler instance = MobileAppUpdateHandler._();

  bool _dialogVisible = false;
  DateTime? _lastSchedule;

  static const _debounce = Duration(seconds: 2);

  static String _browserDownloadNote() {
    if (kIsWeb) {
      return 'Opens in a new tab so you can download the app for your device.';
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.iOS:
        return 'Opens in your browser so you can get the latest iOS build for iPhone or iPad.';
      case TargetPlatform.android:
        return 'Opens in your browser so you can get the latest Android build.';
      default:
        return 'Opens in your browser so you can download the latest app for your device.';
    }
  }

  void tryHandleHttpResponse(http.Response response) {
    if (response.statusCode != 426) return;
    String? message;
    String? code;
    try {
      final body = response.body;
      if (body.isEmpty) return;
      final j = jsonDecode(body);
      if (j is! Map<String, dynamic>) return;
      code = j['error_code'] as String?;
      final err = j['error'];
      message = err is String ? err : err?.toString();
    } catch (_) {
      return;
    }
    if (code != 'APP_UPDATE_REQUIRED') return;
    scheduleShow(message);
  }

  void tryHandleDioException(DioException err) {
    final r = err.response;
    if (r == null || r.statusCode != 426) return;
    final data = r.data;
    if (data is! Map) return;
    final code = data['error_code']?.toString();
    if (code != 'APP_UPDATE_REQUIRED') return;
    final errMsg = data['error'];
    final message = errMsg is String ? errMsg : errMsg?.toString();
    scheduleShow(message);
  }

  void scheduleShow(String? message) {
    final now = DateTime.now();
    if (_lastSchedule != null &&
        now.difference(_lastSchedule!) < _debounce) {
      return;
    }
    _lastSchedule = now;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_dialogVisible) {
        _showDialogImpl(message);
      }
    });
  }

  void _showDialogImpl(String? message) {
    if (_dialogVisible) return;

    final ctx = appNavigatorKey.currentContext;
    if (ctx == null) {
      DebugLogger.logWarn(
          'APP_UPDATE', 'No navigator context yet; retrying shortly');
      Future<void>.delayed(const Duration(milliseconds: 400), () {
        if (!_dialogVisible) {
          final retry = appNavigatorKey.currentContext;
          if (retry != null) {
            _showDialogImpl(message);
          }
        }
      });
      return;
    }

    final bodyText = (message != null && message.trim().isNotEmpty)
        ? message.trim()
        : 'This version of the app is no longer supported. Install the latest release to continue.';

    _dialogVisible = true;
    showDialog<void>(
      context: ctx,
      barrierDismissible: false,
      builder: (dialogContext) {
        final theme = Theme.of(dialogContext);
        final cs = theme.colorScheme;
        final textTheme = theme.textTheme;
        final downloadUri = Uri.parse(AppConfig.mobileAppsDownloadUrl);

        Future<void> openDownloadPage() async {
          try {
            final launched = await launchUrl(
              downloadUri,
              mode: LaunchMode.externalApplication,
            );
            if (!launched) {
              DebugLogger.logWarn('APP_UPDATE', 'launchUrl returned false');
            }
          } catch (e) {
            DebugLogger.logWarn('APP_UPDATE', 'launchUrl failed: $e');
          }
        }

        return PopScope(
          canPop: false,
          child: AlertDialog(
            icon: Icon(
              Icons.system_update_rounded,
              size: 40,
              color: cs.primary,
            ),
            title: Text(
              'Update required',
              textAlign: TextAlign.center,
              style: textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w600,
                letterSpacing: -0.2,
              ),
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    bodyText,
                    style: textTheme.bodyLarge?.copyWith(
                      height: 1.45,
                      color: cs.onSurface,
                    ),
                  ),
                  SizedBox(height: AppSpacing.mdOf(dialogContext)),
                  Text(
                    _browserDownloadNote(),
                    style: textTheme.bodySmall?.copyWith(
                      color: cs.onSurfaceVariant,
                      height: 1.35,
                    ),
                  ),
                ],
              ),
            ),
            actionsAlignment: MainAxisAlignment.center,
            actions: [
              OutlinedButton.icon(
                style: OutlinedButton.styleFrom(
                  foregroundColor: cs.primary,
                  side: BorderSide(color: cs.primary, width: 1.5),
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.lgOf(dialogContext),
                    vertical: AppSpacing.smOf(dialogContext) + 2,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(0),
                  ),
                ),
                onPressed: () async {
                  await openDownloadPage();
                },
                icon: Icon(Icons.open_in_new_rounded, size: 20, color: cs.primary),
                label: Text(
                  'Open download page',
                  style: textTheme.labelLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.2,
                  ),
                ),
              ),
            ],
          ),
        );
      },
    ).whenComplete(() {
      _dialogVisible = false;
    });
  }
}
