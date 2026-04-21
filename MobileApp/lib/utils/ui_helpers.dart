import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'constants.dart';

/// Shows a modal loading overlay with a [CupertinoActivityIndicator] and an
/// optional [message].  The overlay blocks interaction (non-dismissible barrier)
/// and uses theme-aware colors so it looks correct in both light and dark mode.
///
/// Call [dismissAppLoadingOverlay] (or `Navigator.of(context).pop()`) to remove
/// it when the async work finishes.
void showAppLoadingOverlay(BuildContext context, {String? message}) {
  final theme = Theme.of(context);

  showDialog(
    context: context,
    barrierDismissible: false,
    barrierColor: theme.brightness == Brightness.dark
        ? Colors.black54
        : Colors.black26,
    builder: (context) => PopScope(
      canPop: false,
      child: Center(
        child: message == null
            ? const CupertinoActivityIndicator(radius: 16)
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CupertinoActivityIndicator(radius: 16),
                  const SizedBox(height: 16),
                  Material(
                    type: MaterialType.transparency,
                    child: Text(
                      message,
                      style: TextStyle(
                        fontSize: 14,
                        color: theme.colorScheme.onSurface,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ],
              ),
      ),
    ),
  );
}

/// Pops the loading overlay previously shown by [showAppLoadingOverlay].
void dismissAppLoadingOverlay(BuildContext context) {
  Navigator.of(context).pop();
}

/// Shows a themed [SnackBar].
///
/// * [isSuccess] — uses [AppConstants.successColor] background.
/// * [isError]   — uses [AppConstants.errorColor] background.
/// * If neither flag is set the SnackBar falls back to the theme default.
///
/// [duration] defaults to 2 seconds for success / neutral and 3 seconds for
/// errors so transient confirmations disappear faster while errors stay visible
/// a bit longer.
void showAppSnackBar(
  BuildContext context, {
  required String message,
  bool isError = false,
  bool isSuccess = false,
  Duration? duration,
}) {
  final effectiveDuration =
      duration ?? Duration(seconds: isError ? 3 : 2);

  Color? backgroundColor;
  if (isSuccess) {
    backgroundColor = const Color(AppConstants.successColor);
  } else if (isError) {
    backgroundColor = const Color(AppConstants.errorColor);
  }

  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(
        message,
        style: const TextStyle(color: Colors.white),
      ),
      backgroundColor: backgroundColor,
      duration: effectiveDuration,
    ),
  );
}
