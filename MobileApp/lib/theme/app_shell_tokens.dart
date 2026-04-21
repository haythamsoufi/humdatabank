import 'package:flutter/material.dart';

import '../utils/constants.dart';

/// Shell-level semantic colors for the Material app (light/dark).
///
/// Registered on [ThemeData.extensions] from [AppTheme]; use via
/// [Theme.of(context).extension] or [ThemeColors] on [BuildContext].
@immutable
class AppShellTokens extends ThemeExtension<AppShellTokens> {
  const AppShellTokens({
    required this.isDark,
    required this.textPrimary,
    required this.textSecondary,
    required this.surface,
    required this.card,
    required this.border,
    required this.scaffoldBackground,
    required this.divider,
    required this.lightSurface,
    required this.subtleSurface,
    required this.icon,
    required this.disabledText,
    required this.navyText,
    required this.navyIcon,
    required this.navyForeground,
    required this.linkOnSurface,
    required this.navyBase,
    required this.adminHubBlue,
    required this.adminHubPurple,
    required this.adminHubAmber,
    required this.adminHubRed,
    required this.adminHubCyan,
  });

  final bool isDark;

  /// Primary body text (matches [ColorScheme.onSurface] in app themes).
  final Color textPrimary;

  /// Secondary / supporting text.
  final Color textSecondary;

  final Color surface;
  final Color card;
  final Color border;
  final Color scaffoldBackground;
  final Color divider;

  /// Inputs, chips, elevated fills.
  final Color lightSurface;

  /// Subtle section backgrounds.
  final Color subtleSurface;

  final Color icon;
  final Color disabledText;

  /// Brand-aware navy roles (dark mode uses light neutrals for contrast).
  final Color navyText;
  final Color navyIcon;
  final Color navyForeground;

  /// Links and accents on cards / surfaces (lightened primary tint in dark).
  final Color linkOnSurface;

  /// Organization navy for light-mode tinted backgrounds.
  final Color navyBase;

  /// Admin hub shortcut tiles (stable accents; same in light/dark).
  final Color adminHubBlue;
  final Color adminHubPurple;
  final Color adminHubAmber;
  final Color adminHubRed;
  final Color adminHubCyan;

  static AppShellTokens fromBridge({
    required bool isDark,
    required ColorScheme colorScheme,
    required Color navy,
  }) {
    final textPrimary = colorScheme.onSurface;
    final textSecondary = isDark
        ? Colors.white.withValues(alpha: 0.6)
        : const Color(AppConstants.textSecondary);
    final border = isDark
        ? Colors.white.withValues(alpha: 0.12)
        : const Color(AppConstants.borderColor);
    final card = isDark
        ? const Color(AppConstants.themeSurfaceDark)
        : Colors.white;
    final scaffoldBackground = isDark
        ? const Color(AppConstants.themeScaffoldDark)
        : const Color(AppConstants.themeScaffoldLight);
    final divider = isDark
        ? Colors.white.withValues(alpha: 0.15)
        : const Color(AppConstants.borderColor);
    final lightSurface = isDark
        ? const Color(AppConstants.themeElevatedSurfaceDark)
        : const Color(AppConstants.themeInputFillLight);
    final subtleSurface = isDark
        ? const Color(AppConstants.themeSurfaceDark)
        : colorScheme.surfaceContainerLow;
    final icon = isDark ? Colors.white : Colors.black87;
    final disabledText = isDark
        ? Colors.white.withValues(alpha: 0.38)
        : Colors.black.withValues(alpha: 0.38);
    final navyText = isDark ? textPrimary : navy;
    final navyIcon = isDark ? icon : navy;
    final navyForeground = isDark ? textPrimary : navy;
    // Avoid alpha-blending white onto brand navy: on dark greys it reads as a
    // muddy dark blue. Use a fixed light link colour (readable on charcoal).
    final linkOnSurface = isDark
        ? const Color(AppConstants.semanticNotificationSkyLight)
        : colorScheme.primary;

    return AppShellTokens(
      isDark: isDark,
      textPrimary: textPrimary,
      textSecondary: textSecondary,
      surface: colorScheme.surface,
      card: card,
      border: border,
      scaffoldBackground: scaffoldBackground,
      divider: divider,
      lightSurface: lightSurface,
      subtleSurface: subtleSurface,
      icon: icon,
      disabledText: disabledText,
      navyText: navyText,
      navyIcon: navyIcon,
      navyForeground: navyForeground,
      linkOnSurface: linkOnSurface,
      navyBase: navy,
      adminHubBlue: const Color(AppConstants.semanticAdminHubBlue),
      adminHubPurple: const Color(AppConstants.semanticAdminHubPurple),
      adminHubAmber: const Color(AppConstants.semanticAdminHubAmber),
      adminHubRed: const Color(AppConstants.semanticAdminHubRed),
      adminHubCyan: const Color(AppConstants.semanticAdminHubCyan),
    );
  }

  Color navyBackground({double opacity = 0.1}) => isDark
      ? Colors.white.withValues(alpha: opacity)
      : navyBase.withValues(alpha: opacity);

  @override
  AppShellTokens copyWith({
    bool? isDark,
    Color? textPrimary,
    Color? textSecondary,
    Color? surface,
    Color? card,
    Color? border,
    Color? scaffoldBackground,
    Color? divider,
    Color? lightSurface,
    Color? subtleSurface,
    Color? icon,
    Color? disabledText,
    Color? navyText,
    Color? navyIcon,
    Color? navyForeground,
    Color? linkOnSurface,
    Color? navyBase,
    Color? adminHubBlue,
    Color? adminHubPurple,
    Color? adminHubAmber,
    Color? adminHubRed,
    Color? adminHubCyan,
  }) {
    return AppShellTokens(
      isDark: isDark ?? this.isDark,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      surface: surface ?? this.surface,
      card: card ?? this.card,
      border: border ?? this.border,
      scaffoldBackground: scaffoldBackground ?? this.scaffoldBackground,
      divider: divider ?? this.divider,
      lightSurface: lightSurface ?? this.lightSurface,
      subtleSurface: subtleSurface ?? this.subtleSurface,
      icon: icon ?? this.icon,
      disabledText: disabledText ?? this.disabledText,
      navyText: navyText ?? this.navyText,
      navyIcon: navyIcon ?? this.navyIcon,
      navyForeground: navyForeground ?? this.navyForeground,
      linkOnSurface: linkOnSurface ?? this.linkOnSurface,
      navyBase: navyBase ?? this.navyBase,
      adminHubBlue: adminHubBlue ?? this.adminHubBlue,
      adminHubPurple: adminHubPurple ?? this.adminHubPurple,
      adminHubAmber: adminHubAmber ?? this.adminHubAmber,
      adminHubRed: adminHubRed ?? this.adminHubRed,
      adminHubCyan: adminHubCyan ?? this.adminHubCyan,
    );
  }

  @override
  AppShellTokens lerp(ThemeExtension<AppShellTokens>? other, double t) {
    if (other is! AppShellTokens) return this;
    return AppShellTokens(
      isDark: t < 0.5 ? isDark : other.isDark,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      card: Color.lerp(card, other.card, t)!,
      border: Color.lerp(border, other.border, t)!,
      scaffoldBackground:
          Color.lerp(scaffoldBackground, other.scaffoldBackground, t)!,
      divider: Color.lerp(divider, other.divider, t)!,
      lightSurface: Color.lerp(lightSurface, other.lightSurface, t)!,
      subtleSurface: Color.lerp(subtleSurface, other.subtleSurface, t)!,
      icon: Color.lerp(icon, other.icon, t)!,
      disabledText: Color.lerp(disabledText, other.disabledText, t)!,
      navyText: Color.lerp(navyText, other.navyText, t)!,
      navyIcon: Color.lerp(navyIcon, other.navyIcon, t)!,
      navyForeground: Color.lerp(navyForeground, other.navyForeground, t)!,
      linkOnSurface: Color.lerp(linkOnSurface, other.linkOnSurface, t)!,
      navyBase: Color.lerp(navyBase, other.navyBase, t)!,
      adminHubBlue: Color.lerp(adminHubBlue, other.adminHubBlue, t)!,
      adminHubPurple: Color.lerp(adminHubPurple, other.adminHubPurple, t)!,
      adminHubAmber: Color.lerp(adminHubAmber, other.adminHubAmber, t)!,
      adminHubRed: Color.lerp(adminHubRed, other.adminHubRed, t)!,
      adminHubCyan: Color.lerp(adminHubCyan, other.adminHubCyan, t)!,
    );
  }
}
