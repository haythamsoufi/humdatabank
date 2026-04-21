import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/services.dart';
import '../utils/ios_constants.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../l10n/app_localizations.dart';

/// Retry button presentation for [AppErrorState].
enum AppErrorRetryStyle {
  /// Default: Cupertino filled (iOS-style).
  cupertinoFilled,

  /// Outlined button (e.g. Indicator Bank).
  materialOutlined,

  /// Filled button, IFRC red (e.g. Resources).
  materialFilled,
}

/// Standardized error state widget with iOS-style design
class AppErrorState extends StatelessWidget {
  final String? title;
  final String? message;
  final VoidCallback? onRetry;
  final String? retryLabel;
  final IconData? icon;
  final Color? iconColor;

  /// When false, the default/localized title line is omitted (message-only layout).
  final bool showTitle;

  final AppErrorRetryStyle retryStyle;

  const AppErrorState({
    super.key,
    this.title,
    this.message,
    this.onRetry,
    this.retryLabel,
    this.icon,
    this.iconColor,
    this.showTitle = true,
    this.retryStyle = AppErrorRetryStyle.cupertinoFilled,
  });

  /// Offline / connectivity-style icon and copy layout (wifi icon, no "Oops" title).
  factory AppErrorState.network({
    Key? key,
    required String message,
    VoidCallback? onRetry,
    String? retryLabel,
    AppErrorRetryStyle retryStyle = AppErrorRetryStyle.materialFilled,
  }) {
    return AppErrorState(
      key: key,
      title: null,
      message: message,
      onRetry: onRetry,
      retryLabel: retryLabel,
      icon: Icons.wifi_off_rounded,
      iconColor: null,
      showTitle: false,
      retryStyle: retryStyle,
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isDark = theme.isDarkTheme;

    final errorIcon = icon ?? Icons.error_outline_rounded;
    final errorIconColor = iconColor ??
        (isDark
            ? IOSColors.systemRed
            : const Color(AppConstants.errorColor));

    final errorTitle = title ?? localizations.oopsSomethingWentWrong;
    final errorMessage = message ?? localizations.somethingWentWrong;

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: IOSSpacing.xxl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Error icon
            Container(
              padding: const EdgeInsets.all(IOSSpacing.xl),
              decoration: BoxDecoration(
                color: errorIconColor.withValues(alpha: isDark ? 0.15 : 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                errorIcon,
                size: 56,
                color: errorIconColor,
              ),
            ),
            const SizedBox(height: IOSSpacing.xl),

            if (showTitle) ...[
              Text(
                errorTitle,
                style: IOSTextStyle.title2(context),
                textAlign: TextAlign.center,
              ),
              if (message != null) const SizedBox(height: IOSSpacing.sm),
            ],

            if (message != null)
              Text(
                errorMessage,
                style: IOSTextStyle.subheadline(context).copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),

            if (onRetry != null) ...[
              const SizedBox(height: IOSSpacing.xxl),
              _RetryButton(
                label: retryLabel ?? localizations.retry,
                style: retryStyle,
                onPressed: onRetry!,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _RetryButton extends StatelessWidget {
  const _RetryButton({
    required this.label,
    required this.style,
    required this.onPressed,
  });

  final String label;
  final AppErrorRetryStyle style;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    // [AppConstants.ifrcRed] is a getter — not a const; avoid const ButtonStyle trees.
    final ifrcRedColor = Color(AppConstants.ifrcRed);

    switch (style) {
      case AppErrorRetryStyle.cupertinoFilled:
        return Semantics(
          label: label,
          hint: localizations.retry,
          button: true,
          child: cupertino.CupertinoButton.filled(
            onPressed: () {
              HapticFeedback.mediumImpact();
              onPressed();
            },
            padding: const EdgeInsets.symmetric(
              horizontal: IOSSpacing.xxl,
              vertical: IOSSpacing.md,
            ),
            borderRadius: BorderRadius.circular(10),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.refresh_rounded,
                  size: 18,
                  color: Theme.of(context).colorScheme.onPrimary,
                ),
                const SizedBox(width: 6),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: Theme.of(context).colorScheme.onPrimary,
                    letterSpacing: -0.2,
                  ),
                ),
              ],
            ),
          ),
        );
      case AppErrorRetryStyle.materialOutlined:
        return Semantics(
          label: label,
          button: true,
          child: OutlinedButton.icon(
            onPressed: () {
              HapticFeedback.mediumImpact();
              onPressed();
            },
            icon: Icon(Icons.refresh_rounded, size: 18, color: ifrcRedColor),
            label: Text(label),
            style: OutlinedButton.styleFrom(
              foregroundColor: ifrcRedColor,
              side: BorderSide(color: ifrcRedColor),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
              ),
            ),
          ),
        );
      case AppErrorRetryStyle.materialFilled:
        return Semantics(
          label: label,
          button: true,
          child: FilledButton.icon(
            onPressed: () {
              HapticFeedback.mediumImpact();
              onPressed();
            },
            icon: const Icon(Icons.refresh_rounded, size: 18, color: Colors.white),
            label: Text(label),
            style: FilledButton.styleFrom(
              backgroundColor: ifrcRedColor,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            ),
          ),
        );
    }
  }
}
