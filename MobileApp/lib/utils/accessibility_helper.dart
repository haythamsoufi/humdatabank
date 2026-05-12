import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

/// Helper class for accessibility utilities
class AccessibilityHelper {
  /// Calculate contrast ratio between two colors
  /// Returns a value between 1 (no contrast) and 21 (maximum contrast)
  /// WCAG AA requires 4.5:1 for normal text, 3:1 for large text
  static double calculateContrastRatio(Color foreground, Color background) {
    final fgLuminance = _getRelativeLuminance(foreground);
    final bgLuminance = _getRelativeLuminance(background);

    final lighter = fgLuminance > bgLuminance ? fgLuminance : bgLuminance;
    final darker = fgLuminance > bgLuminance ? bgLuminance : fgLuminance;

    return (lighter + 0.05) / (darker + 0.05);
  }

  /// Get relative luminance of a color (0-1)
  static double _getRelativeLuminance(Color color) {
    final r = _linearizeColorComponent(color.r);
    final g = _linearizeColorComponent(color.g);
    final b = _linearizeColorComponent(color.b);

    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  /// Linearize color component for luminance calculation
  static double _linearizeColorComponent(double component) {
    if (component <= 0.03928) {
      return component / 12.92;
    }
    return math.pow((component + 0.055) / 1.055, 2.4).toDouble();
  }

  /// Check if contrast meets WCAG AA standard (4.5:1 for normal text)
  static bool meetsWCAGAA(Color foreground, Color background) {
    return calculateContrastRatio(foreground, background) >= 4.5;
  }

  /// Check if contrast meets WCAG AAA standard (7:1 for normal text)
  static bool meetsWCAGAAA(Color foreground, Color background) {
    return calculateContrastRatio(foreground, background) >= 7.0;
  }

  /// Get accessible text color for a given background
  /// Returns white or black based on which provides better contrast
  static Color getAccessibleTextColor(Color background) {
    final whiteContrast = calculateContrastRatio(Colors.white, background);
    final blackContrast = calculateContrastRatio(Colors.black, background);

    return whiteContrast > blackContrast ? Colors.white : Colors.black;
  }

  /// Foreground for text and icons on saturated brand-color hero strips (e.g. admin profile banner).
  /// Uses light ink on deep or saturated mid-tone brand colors; soft dark on very light pastels so
  /// badges and rings stay readable without a heavy black ring on orange/red gradients.
  static Color bannerHeroForeground(Color brand) {
    final hsv = HSVColor.fromColor(brand);
    final lum = brand.computeLuminance();
    if (lum < 0.38) {
      return const Color(0xFFF5F5F5);
    }
    if (hsv.saturation > 0.22 && hsv.value > 0.48 && lum < 0.82) {
      return const Color(0xFFF5F5F5);
    }
    return const Color(0xE6161616);
  }

  /// Creates a semantic label for form fields, appending required/error state.
  static String formFieldSemanticLabel(
    String label, {
    bool isRequired = false,
    String? errorText,
  }) {
    final buffer = StringBuffer(label);
    if (isRequired) buffer.write(', required');
    if (errorText != null) buffer.write(', error: $errorText');
    return buffer.toString();
  }

  /// Creates a semantic label for list items with position info.
  static String listItemSemanticLabel(
    String label, {
    required int index,
    required int total,
  }) {
    return '$label, item ${index + 1} of $total';
  }

  /// Creates a semantic label for toggle controls.
  static String toggleSemanticLabel(String label, {required bool isOn}) {
    return '$label, ${isOn ? 'on' : 'off'}';
  }

  /// Announces a message to screen readers via [SemanticsService].
  static void announce(BuildContext context, String message) {
    SemanticsService.sendAnnouncement(View.of(context), message, Directionality.of(context));
  }
}
