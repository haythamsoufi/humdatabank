import 'package:flutter/material.dart';
import 'constants.dart';

/// Extension on BuildContext to easily access theme-aware colors
extension ThemeColors on BuildContext {
  /// Gets the appropriate text color for the current theme
  Color get textColor => Theme.of(this).colorScheme.onSurface;

  /// Gets the appropriate secondary text color for the current theme
  Color get textSecondaryColor => Theme.of(this).brightness == Brightness.dark
      ? Colors.white.withOpacity(0.6)
      : const Color(AppConstants.textSecondary);

  /// Gets the appropriate surface/background color for the current theme
  Color get surfaceColor => Theme.of(this).colorScheme.surface;

  /// Gets the appropriate card color for the current theme
  Color get cardColor => Theme.of(this).cardColor;

  /// Gets the appropriate border color for the current theme
  Color get borderColor => Theme.of(this).brightness == Brightness.dark
      ? Colors.white.withOpacity(0.12)
      : const Color(AppConstants.borderColor);

  /// Gets the appropriate scaffold background color for the current theme
  Color get scaffoldBackgroundColor => Theme.of(this).scaffoldBackgroundColor;

  /// Gets the appropriate divider color for the current theme
  Color get dividerColor => Theme.of(this).dividerColor;

  /// Gets a light surface color (for inputs, chips, etc.)
  Color get lightSurfaceColor => Theme.of(this).brightness == Brightness.dark
      ? const Color(0xFF2C2C2C)
      : const Color(0xFFFAFAFA);

  /// Gets an even lighter surface color (for subtle backgrounds)
  Color get subtleSurfaceColor => Theme.of(this).brightness == Brightness.dark
      ? const Color(0xFF1E1E1E)
      : Colors.grey.shade50;

  /// Gets the appropriate icon color for the current theme
  Color get iconColor =>
      Theme.of(this).iconTheme.color ??
      (Theme.of(this).brightness == Brightness.dark
          ? Colors.white
          : Colors.black87);

  /// Gets disabled text color
  Color get disabledTextColor => Theme.of(this).brightness == Brightness.dark
      ? Colors.white.withOpacity(0.38)
      : Colors.black.withOpacity(0.38);

  /// Gets theme-aware navy color for text and icons
  /// In dark theme, returns light text color for better contrast
  /// In light theme, returns the IFRC navy color
  Color get navyTextColor => Theme.of(this).brightness == Brightness.dark
      ? textColor
      : Color(AppConstants.ifrcNavy);

  /// Gets theme-aware navy color for icons
  /// In dark theme, returns icon color for better visibility
  /// In light theme, returns the IFRC navy color
  Color get navyIconColor => Theme.of(this).brightness == Brightness.dark
      ? iconColor
      : Color(AppConstants.ifrcNavy);

  /// Gets theme-aware navy color for button foreground/text
  /// In dark theme, returns text color for better contrast
  /// In light theme, returns the IFRC navy color
  Color get navyForegroundColor => Theme.of(this).brightness == Brightness.dark
      ? textColor
      : Color(AppConstants.ifrcNavy);

  /// Gets theme-aware navy background color with opacity
  /// In dark theme, uses white with opacity for subtle backgrounds
  /// In light theme, uses navy with opacity
  Color navyBackgroundColor({double opacity = 0.1}) =>
      Theme.of(this).brightness == Brightness.dark
          ? Colors.white.withOpacity(opacity)
          : Color(AppConstants.ifrcNavy).withOpacity(opacity);
}

/// Extension on ThemeData for additional theme-aware color helpers
extension AppThemeColors on ThemeData {
  /// Gets text color with proper contrast
  Color getTextColor({double opacity = 1.0}) {
    return brightness == Brightness.dark
        ? Colors.white.withOpacity(opacity)
        : const Color(AppConstants.textColor).withOpacity(opacity);
  }

  /// Gets secondary text color with proper contrast
  Color getSecondaryTextColor({double opacity = 1.0}) {
    return brightness == Brightness.dark
        ? Colors.white.withOpacity(0.6 * opacity)
        : const Color(AppConstants.textSecondary).withOpacity(opacity);
  }

  /// Gets border color appropriate for the theme
  Color getBorderColor({double opacity = 1.0}) {
    return brightness == Brightness.dark
        ? Colors.white.withOpacity(0.12 * opacity)
        : const Color(AppConstants.borderColor).withOpacity(opacity);
  }

  /// Gets a surface color for input fields
  Color getInputSurfaceColor() {
    return brightness == Brightness.dark
        ? const Color(0xFF2C2C2C)
        : const Color(0xFFFAFAFA);
  }
}

/// Helper class for creating theme-aware colors with proper contrast
class ThemeAwareColors {
  /// Gets a color that ensures proper contrast based on background brightness
  static Color ensureContrast(
    Color color,
    Brightness backgroundBrightness, {
    double minContrast = 4.5, // WCAG AA standard for normal text
  }) {
    // For dark backgrounds, use lighter version
    // For light backgrounds, use darker version
    if (backgroundBrightness == Brightness.dark) {
      // Ensure color is light enough for dark background
      final luminance = color.computeLuminance();
      if (luminance < 0.4) {
        // Too dark, lighten it
        return color.withOpacity(1.0);
      }
    } else {
      // Ensure color is dark enough for light background
      final luminance = color.computeLuminance();
      if (luminance > 0.6) {
        // Too light, darken it
        return color.withOpacity(1.0);
      }
    }
    return color;
  }

  /// Gets text color that ensures WCAG contrast compliance
  static Color getContrastTextColor(Color backgroundColor) {
    final luminance = backgroundColor.computeLuminance();
    // If background is dark, return light text
    // If background is light, return dark text
    return luminance > 0.5
        ? const Color(AppConstants.textColor) // Dark text for light background
        : Colors.white; // Light text for dark background
  }

  /// Adapts a color based on theme brightness
  static Color adaptColor(
      Color lightColor, Color darkColor, Brightness brightness) {
    return brightness == Brightness.dark ? darkColor : lightColor;
  }
}
