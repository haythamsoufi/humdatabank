import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/services.dart';
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';
import '../l10n/app_localizations.dart';

/// Standardized error state widget with iOS-style design
class AppErrorState extends StatelessWidget {
  final String? title;
  final String? message;
  final VoidCallback? onRetry;
  final String? retryLabel;
  final IconData? icon;
  final Color? iconColor;

  const AppErrorState({
    super.key,
    this.title,
    this.message,
    this.onRetry,
    this.retryLabel,
    this.icon,
    this.iconColor,
  });

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final errorIcon = icon ?? Icons.error_outline_rounded;
    final errorIconColor = iconColor ??
        (isDark
            ? IOSColors.systemRed
            : const Color(0xFFDC2626));

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
                color: errorIconColor.withOpacity(isDark ? 0.15 : 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                errorIcon,
                size: 56,
                color: errorIconColor,
              ),
            ),
            const SizedBox(height: IOSSpacing.xl),

            // Error title
            Text(
              errorTitle,
              style: IOSTextStyle.title2(context),
              textAlign: TextAlign.center,
            ),

            if (message != null) ...[
              const SizedBox(height: IOSSpacing.sm),
              Text(
                errorMessage,
                style: IOSTextStyle.subheadline(context).copyWith(
                  color: theme.colorScheme.onSurface.withOpacity(0.6),
                  height: 1.4,
                ),
                textAlign: TextAlign.center,
              ),
            ],

            // Retry button
            if (onRetry != null) ...[
              const SizedBox(height: IOSSpacing.xxl),
              Semantics(
                label: retryLabel ?? localizations.retry,
                hint: localizations.retry,
                button: true,
                child: cupertino.CupertinoButton.filled(
                  onPressed: () {
                    HapticFeedback.mediumImpact();
                    onRetry!();
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
                        color: Colors.white,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        retryLabel ?? localizations.retry,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                          letterSpacing: -0.2,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
