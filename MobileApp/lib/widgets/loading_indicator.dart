import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import '../l10n/app_localizations.dart';

/// Standardized loading indicator widget for consistent UX across the app
class AppLoadingIndicator extends StatelessWidget {
  final String? message;
  final Color? color;
  final double? size;
  final bool useIOSStyle;

  const AppLoadingIndicator({
    super.key,
    this.message,
    this.color,
    this.size,
    this.useIOSStyle = true,
  });

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final loadingColor = color ?? theme.colorScheme.primary;
    final loadingSize = size ?? 20.0;

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Semantics(
            label: message ?? localizations?.loading ?? 'Loading',
            child: useIOSStyle
                ? cupertino.CupertinoActivityIndicator(
                    radius: loadingSize / 2,
                    color: loadingColor,
                  )
                : CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(loadingColor),
                    strokeWidth: 2.5,
                  ),
          ),
          if (message != null) ...[
            const SizedBox(height: 16),
            Text(
              message!,
              style: TextStyle(
                color: theme.colorScheme.onSurface.withOpacity(0.6),
                fontSize: 15,
                fontWeight: FontWeight.w400,
                letterSpacing: -0.2,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ],
      ),
    );
  }
}

/// Full-screen loading indicator with message
class AppFullScreenLoading extends StatelessWidget {
  final String? message;
  final Color? color;
  final bool useIOSStyle;

  const AppFullScreenLoading({
    super.key,
    this.message,
    this.color,
    this.useIOSStyle = true,
  });

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final loadingColor = color ?? theme.colorScheme.primary;

    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Semantics(
              label: message ?? localizations?.loading ?? 'Loading',
              child: useIOSStyle
                  ? cupertino.CupertinoActivityIndicator(
                      radius: 10,
                      color: loadingColor,
                    )
                  : CircularProgressIndicator(
                      valueColor: AlwaysStoppedAnimation<Color>(loadingColor),
                      strokeWidth: 2.5,
                    ),
            ),
            if (message != null) ...[
              const SizedBox(height: 16),
              Text(
                message!,
                style: TextStyle(
                  color: theme.colorScheme.onSurface.withOpacity(0.6),
                  fontSize: 15,
                  fontWeight: FontWeight.w400,
                  letterSpacing: -0.2,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
