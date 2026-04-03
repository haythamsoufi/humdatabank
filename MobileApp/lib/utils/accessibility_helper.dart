import 'dart:math' as math;
import 'package:flutter/material.dart';

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
    final r = _linearizeColorComponent(color.red / 255.0);
    final g = _linearizeColorComponent(color.green / 255.0);
    final b = _linearizeColorComponent(color.blue / 255.0);

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
}
