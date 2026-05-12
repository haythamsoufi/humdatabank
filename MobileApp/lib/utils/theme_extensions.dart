import 'package:flutter/material.dart';

import '../theme/app_shell_tokens.dart';
import 'constants.dart';

/// Whether the resolved [ThemeData] is dark (same as [Theme.brightness]).
extension AppThemeDataX on ThemeData {
  bool get isDarkTheme => brightness == Brightness.dark;

  /// Card/list ambient shadow (theme-relative opacity).
  Color ambientShadow({double lightOpacity = 0.05, double darkOpacity = 0.32}) =>
      isDarkTheme
          ? Colors.black.withValues(alpha: darkOpacity)
          : Colors.black.withValues(alpha: lightOpacity);

  // --- Quiz: option / result surfaces (success + error from [AppConstants]) ---

  Color quizOptionResultCorrectFill() => isDarkTheme
      ? const Color(AppConstants.successColor).withValues(alpha: 0.30)
      : const Color(AppConstants.successColor).withValues(alpha: 0.12);

  Color quizOptionResultWrongFill() => isDarkTheme
      ? const Color(AppConstants.errorColor).withValues(alpha: 0.28)
      : const Color(AppConstants.errorColor).withValues(alpha: 0.12);

  Color quizOptionResultCorrectBorder() => const Color(AppConstants.successColor)
      .withValues(alpha: isDarkTheme ? 0.95 : 0.85);

  Color quizOptionResultWrongBorder() => const Color(AppConstants.errorColor)
      .withValues(alpha: isDarkTheme ? 0.95 : 0.85);

  Color quizOptionResultCorrectIconBg() => isDarkTheme
      ? const Color(AppConstants.successColor).withValues(alpha: 0.45)
      : const Color(AppConstants.successColor).withValues(alpha: 0.22);

  Color quizOptionResultWrongIconBg() => isDarkTheme
      ? const Color(AppConstants.errorColor).withValues(alpha: 0.45)
      : const Color(AppConstants.errorColor).withValues(alpha: 0.22);

  Color quizOptionResultCorrectIconFg() => isDarkTheme
      ? const Color(0xFFDCFCE7)
      : const Color(AppConstants.successColor);

  Color quizOptionResultWrongIconFg() => isDarkTheme
      ? const Color(0xFFFEE2E2)
      : const Color(AppConstants.errorColor);

  Color quizOptionResultCorrectText() => isDarkTheme
      ? const Color(0xFFDCFCE7)
      : const Color(0xFF14532D);

  Color quizOptionResultWrongText() => isDarkTheme
      ? const Color(0xFFFEE2E2)
      : const Color(0xFF7F1D1D);

  Color quizOptionResultShadow(bool isCorrect, bool isWrong) {
    if (isCorrect) {
      return const Color(AppConstants.successColor).withValues(alpha: 0.3);
    }
    if (isWrong) {
      return const Color(AppConstants.errorColor).withValues(alpha: 0.3);
    }
    return ambientShadow(lightOpacity: 0.1, darkOpacity: 0.35);
  }
}

/// Extension on BuildContext to easily access theme-aware colors
extension ThemeColors on BuildContext {
  AppShellTokens get _shell {
    final t = Theme.of(this).extension<AppShellTokens>();
    assert(() {
      if (t == null) {
        debugPrint(
          'ThemeColors: AppShellTokens missing from ThemeData.extensions — '
          'ensure AppTheme registers it.',
        );
      }
      return true;
    }());
    return t ??
        AppShellTokens.fromBridge(
          isDark: Theme.of(this).brightness == Brightness.dark,
          colorScheme: Theme.of(this).colorScheme,
          navy: Color(AppConstants.ifrcNavy),
        );
  }

  /// True when the current [Theme] resolves to dark mode (includes system + OS dark).
  bool get isDarkTheme => Theme.of(this).brightness == Brightness.dark;

  /// Gets the appropriate text color for the current theme
  Color get textColor => _shell.textPrimary;

  /// Gets the appropriate secondary text color for the current theme
  Color get textSecondaryColor => _shell.textSecondary;

  /// Gets the appropriate surface/background color for the current theme
  Color get surfaceColor => _shell.surface;

  /// Gets the appropriate card color for the current theme
  Color get cardColor => _shell.card;

  /// Gets the appropriate border color for the current theme
  Color get borderColor => _shell.border;

  /// Gets the appropriate scaffold background color for the current theme
  Color get scaffoldBackgroundColor => _shell.scaffoldBackground;

  /// Gets the appropriate divider color for the current theme
  Color get dividerColor => _shell.divider;

  /// Gets a light surface color (for inputs, chips, etc.)
  Color get lightSurfaceColor => _shell.lightSurface;

  /// Gets an even lighter surface color (for subtle backgrounds)
  Color get subtleSurfaceColor => _shell.subtleSurface;

  /// Gets the appropriate icon color for the current theme
  Color get iconColor =>
      Theme.of(this).iconTheme.color ?? _shell.icon;

  /// Gets disabled text color
  Color get disabledTextColor => _shell.disabledText;

  /// Gets theme-aware navy color for text and icons
  /// In dark theme, returns light text color for better contrast
  /// In light theme, returns the IFRC navy color
  Color get navyTextColor => _shell.navyText;

  /// Gets theme-aware navy color for icons
  /// In dark theme, returns icon color for better visibility
  /// In light theme, returns the IFRC navy color
  Color get navyIconColor => _shell.navyIcon;

  /// Gets theme-aware navy color for button foreground/text
  /// In dark theme, returns text color for better contrast
  /// In light theme, returns the IFRC navy color
  Color get navyForegroundColor => _shell.navyForeground;

  /// Links, [TextButton]s, HTML anchors, and small accents drawn **on** surfaces (cards, chat, search chrome).
  ///
  /// [ColorScheme.primary] is brand navy (~`#011E41`). On light backgrounds it reads as a normal link colour.
  /// On dark greys it is nearly the same luminance as the surface, so it must not be used as plain text/link
  /// colour there — use this getter instead (lightened brand tint in dark mode).
  Color get linkOnSurfaceColor => _shell.linkOnSurface;

  /// Admin dashboard shortcut tile accents ([AppShellTokens]).
  Color get adminHubBlue => _shell.adminHubBlue;
  Color get adminHubPurple => _shell.adminHubPurple;
  Color get adminHubAmber => _shell.adminHubAmber;
  Color get adminHubRed => _shell.adminHubRed;
  Color get adminHubCyan => _shell.adminHubCyan;

  /// Gets theme-aware navy background color with opacity
  /// In dark theme, uses white with opacity for subtle backgrounds
  /// In light theme, uses navy with opacity
  Color navyBackgroundColor({double opacity = 0.1}) =>
      _shell.navyBackground(opacity: opacity);
}

/// Offline / sync strip colors (compact indicator row).
extension OfflineStatusColors on BuildContext {
  Color get offlineQueuedBackground => isDarkTheme
      ? Colors.orange.shade900.withValues(alpha: 0.45)
      : Colors.orange.shade100;

  Color get offlineQueuedForeground => isDarkTheme
      ? Colors.orange.shade100
      : Colors.orange.shade900;

  Color get offlineSyncedBackground => isDarkTheme
      ? const Color(AppConstants.successColor).withValues(alpha: 0.24)
      : const Color(AppConstants.successColor).withValues(alpha: 0.12);

  Color get offlineSyncedForeground => isDarkTheme
      ? Colors.green.shade200
      : Colors.green.shade800;

  /// Offline / no-radio — solid warning tones (fully opaque).
  Color get offlineDisconnectedInlineBackground =>
      isDarkTheme ? const Color(0xFF422006) : const Color(0xFFFFF7ED);

  Color get offlineDisconnectedInlineForeground =>
      isDarkTheme ? const Color(0xFFFDE68A) : const Color(0xFF9A3412);
}

