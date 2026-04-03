import 'package:flutter/material.dart';

/// iOS System Colors
class IOSColors {
  // System Blue
  static const Color systemBlue = Color(0xFF007AFF);
  static const Color systemBlueDark = Color(0xFF0A84FF);

  // System Gray
  static const Color systemGray = Color(0xFF8E8E93);
  static const Color systemGray2 = Color(0xFFAEAEB2);
  static const Color systemGray3 = Color(0xFFC7C7CC);
  static const Color systemGray4 = Color(0xFFD1D1D6);
  static const Color systemGray5 = Color(0xFFE5E5EA);
  static const Color systemGray6 = Color(0xFFF2F2F7);

  // System Green (Success)
  static const Color systemGreen = Color(0xFF34C759);

  // System Red (Error)
  static const Color systemRed = Color(0xFFFF3B30);

  // System Orange (Warning)
  static const Color systemOrange = Color(0xFFFF9500);

  // System Yellow
  static const Color systemYellow = Color(0xFFFFCC00);

  // Background colors
  static const Color systemBackground = Color(0xFFF2F2F7);
  static const Color systemBackgroundDark = Color(0xFF000000);
  static const Color secondarySystemBackground = Color(0xFFFFFFFF);
  static const Color secondarySystemBackgroundDark = Color(0xFF1C1C1E);

  // Grouped table view background
  static const Color groupedTableViewBackground = Color(0xFFEFEFF4);
  static const Color groupedTableViewBackgroundDark = Color(0xFF000000);

  /// Get theme-aware system blue
  static Color getSystemBlue(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? systemBlueDark
        : systemBlue;
  }

  /// Get theme-aware grouped background
  static Color getGroupedBackground(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? groupedTableViewBackgroundDark
        : groupedTableViewBackground;
  }
}

/// iOS Standard Spacing
///
/// Base spacing values (for reference, use context-aware methods below)
class IOSSpacing {
  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 16.0;
  static const double lg = 20.0;
  static const double xl = 24.0;
  static const double xxl = 32.0;

  // Base screen width for scaling (iPhone 12/13 standard: 390 logical pixels)
  static const double _baseScreenWidth = 390.0;

  // Minimum and maximum scale factors to prevent extreme scaling
  static const double _minScale = 0.85;
  static const double _maxScale = 1.25;

  /// Get scale factor based on screen width
  /// Scales proportionally to base width (390) with min/max bounds
  static double getScaleFactor(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final scale = screenWidth / _baseScreenWidth;

    // Clamp scale to prevent extreme scaling on very small or very large screens
    return scale.clamp(_minScale, _maxScale);
  }

  /// Get scaled spacing value based on device screen size
  /// Use this instead of direct constants for responsive design
  static double scaled(BuildContext context, double baseValue) {
    return baseValue * getScaleFactor(context);
  }

  /// Context-aware spacing values that scale with screen size
  static double xsOf(BuildContext context) => scaled(context, xs);
  static double smOf(BuildContext context) => scaled(context, sm);
  static double mdOf(BuildContext context) => scaled(context, md);
  static double lgOf(BuildContext context) => scaled(context, lg);
  static double xlOf(BuildContext context) => scaled(context, xl);
  static double xxlOf(BuildContext context) => scaled(context, xxl);

  /// Helper methods for creating scaled EdgeInsets
  static EdgeInsets all(BuildContext context, double value) {
    return EdgeInsets.all(scaled(context, value));
  }

  static EdgeInsets symmetric(BuildContext context, {
    double? horizontal,
    double? vertical,
  }) {
    return EdgeInsets.symmetric(
      horizontal: horizontal != null ? scaled(context, horizontal) : 0,
      vertical: vertical != null ? scaled(context, vertical) : 0,
    );
  }

  static EdgeInsets only(BuildContext context, {
    double? left,
    double? top,
    double? right,
    double? bottom,
  }) {
    return EdgeInsets.only(
      left: left != null ? scaled(context, left) : 0,
      top: top != null ? scaled(context, top) : 0,
      right: right != null ? scaled(context, right) : 0,
      bottom: bottom != null ? scaled(context, bottom) : 0,
    );
  }

  static EdgeInsets fromLTRB(BuildContext context, double left, double top, double right, double bottom) {
    return EdgeInsets.fromLTRB(
      scaled(context, left),
      scaled(context, top),
      scaled(context, right),
      scaled(context, bottom),
    );
  }
}

/// iOS Typography Scale
class IOSTextStyle {
  // Base font sizes (iOS standard)
  static const double _largeTitleSize = 34.0;
  static const double _title1Size = 28.0;
  static const double _title2Size = 22.0;
  static const double _title3Size = 20.0;
  static const double _headlineSize = 17.0;
  static const double _bodySize = 17.0;
  static const double _calloutSize = 16.0;
  static const double _subheadlineSize = 15.0;
  static const double _footnoteSize = 13.0;
  static const double _caption1Size = 12.0;
  static const double _caption2Size = 11.0;

  // Base screen width for scaling (iPhone 12/13 standard: 390 logical pixels)
  static const double _baseScreenWidth = 390.0;

  // Text scaling factors (typically more conservative than spacing)
  static const double _minTextScale = 0.9;
  static const double _maxTextScale = 1.2;

  /// Get text scale factor based on screen width
  /// Text scales more conservatively than spacing
  static double getTextScaleFactor(BuildContext context) {
    final screenWidth = MediaQuery.of(context).size.width;
    final scale = screenWidth / _baseScreenWidth;

    // Clamp text scale more conservatively than spacing
    return scale.clamp(_minTextScale, _maxTextScale);
  }

  /// Get scaled font size based on device screen size
  static double _scaledFontSize(BuildContext context, double baseSize) {
    return baseSize * getTextScaleFactor(context);
  }

  static TextStyle largeTitle(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _largeTitleSize),
      fontWeight: FontWeight.w700,
      letterSpacing: 0.37,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle title1(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _title1Size),
      fontWeight: FontWeight.w700,
      letterSpacing: 0.36,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle title2(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _title2Size),
      fontWeight: FontWeight.w700,
      letterSpacing: 0.35,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle title3(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _title3Size),
      fontWeight: FontWeight.w600,
      letterSpacing: 0.38,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle headline(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _headlineSize),
      fontWeight: FontWeight.w600,
      letterSpacing: -0.41,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle body(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _bodySize),
      fontWeight: FontWeight.w400,
      letterSpacing: -0.41,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle callout(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _calloutSize),
      fontWeight: FontWeight.w400,
      letterSpacing: -0.32,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle subheadline(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _subheadlineSize),
      fontWeight: FontWeight.w400,
      letterSpacing: -0.24,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle footnote(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _footnoteSize),
      fontWeight: FontWeight.w400,
      letterSpacing: -0.08,
      color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
    );
  }

  static TextStyle caption1(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _caption1Size),
      fontWeight: FontWeight.w400,
      letterSpacing: 0,
      color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
    );
  }

  static TextStyle caption2(BuildContext context) {
    return TextStyle(
      fontSize: _scaledFontSize(context, _caption2Size),
      fontWeight: FontWeight.w400,
      letterSpacing: 0.07,
      color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
    );
  }
}

/// iOS Animation Curves
class IOSCurves {
  static const Curve easeInOut = Curves.easeInOutCubic;
  static const Curve easeOut = Curves.easeOutCubic;
  static const Curve easeIn = Curves.easeInCubic;
}

/// iOS Icon Sizes - Responsive scaling for icons
class IOSIconSize {
  // Base icon sizes (iOS standard)
  static const double small = 12.0;
  static const double medium = 16.0;
  static const double regular = 20.0;
  static const double large = 24.0;
  static const double xlarge = 32.0;

  /// Get scaled icon size based on device screen size
  /// Use this for icons to ensure they scale appropriately
  static double scaled(BuildContext context, double baseSize) {
    return baseSize * IOSSpacing.getScaleFactor(context);
  }

  /// Context-aware icon sizes that scale with screen size
  static double smallOf(BuildContext context) => scaled(context, small);
  static double mediumOf(BuildContext context) => scaled(context, medium);
  static double regularOf(BuildContext context) => scaled(context, regular);
  static double largeOf(BuildContext context) => scaled(context, large);
  static double xlargeOf(BuildContext context) => scaled(context, xlarge);
}

/// iOS Component Dimensions - Responsive scaling for component sizes
class IOSDimensions {
  // Base border radius (iOS standard)
  static const double borderRadiusSmall = 8.0;
  static const double borderRadiusMedium = 10.0;
  static const double borderRadiusLarge = 14.0;
  static const double borderRadiusXLarge = 24.0;

  /// Get scaled border radius based on device screen size
  static double scaledBorderRadius(BuildContext context, double baseRadius) {
    return baseRadius * IOSSpacing.getScaleFactor(context);
  }

  /// Context-aware border radius values
  static double borderRadiusSmallOf(BuildContext context) => scaledBorderRadius(context, borderRadiusSmall);
  static double borderRadiusMediumOf(BuildContext context) => scaledBorderRadius(context, borderRadiusMedium);
  static double borderRadiusLargeOf(BuildContext context) => scaledBorderRadius(context, borderRadiusLarge);
  static double borderRadiusXLargeOf(BuildContext context) => scaledBorderRadius(context, borderRadiusXLarge);
}
