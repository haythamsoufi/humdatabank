import 'package:flutter/material.dart';

import 'app_spacing.dart';
import 'layout_scale.dart';
import 'theme_extensions.dart';

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
    return context.isDarkTheme ? systemBlueDark : systemBlue;
  }

  /// Get theme-aware grouped background
  static Color getGroupedBackground(BuildContext context) {
    return context.isDarkTheme
        ? groupedTableViewBackgroundDark
        : groupedTableViewBackground;
  }
}

/// Back-compat alias: iOS and Material both use [AppSpacing].
class IOSSpacing {
  static const double xs = AppSpacing.xs;
  static const double sm = AppSpacing.sm;
  static const double md = AppSpacing.md;
  static const double lg = AppSpacing.lg;
  static const double xl = AppSpacing.xl;
  static const double xxl = AppSpacing.xxl;

  static double getScaleFactor(BuildContext context) =>
      AppSpacing.getScaleFactor(context);

  static double scaled(BuildContext context, double baseValue) =>
      AppSpacing.scaled(context, baseValue);

  static double xsOf(BuildContext context) => AppSpacing.xsOf(context);
  static double smOf(BuildContext context) => AppSpacing.smOf(context);
  static double mdOf(BuildContext context) => AppSpacing.mdOf(context);
  static double lgOf(BuildContext context) => AppSpacing.lgOf(context);
  static double xlOf(BuildContext context) => AppSpacing.xlOf(context);
  static double xxlOf(BuildContext context) => AppSpacing.xxlOf(context);

  static EdgeInsets all(BuildContext context, double value) =>
      AppSpacing.all(context, value);

  static EdgeInsets symmetric(
    BuildContext context, {
    double? horizontal,
    double? vertical,
  }) =>
      AppSpacing.symmetric(context, horizontal: horizontal, vertical: vertical);

  static EdgeInsets only(
    BuildContext context, {
    double? left,
    double? top,
    double? right,
    double? bottom,
  }) =>
      AppSpacing.only(
        context,
        left: left,
        top: top,
        right: right,
        bottom: bottom,
      );

  static EdgeInsets fromLTRB(
    BuildContext context,
    double left,
    double top,
    double right,
    double bottom,
  ) =>
      AppSpacing.fromLTRB(context, left, top, right, bottom);
}

/// iOS-named styles mapped to [ThemeData.textTheme].
///
/// Font sizes and [LayoutScale] are applied once in [MaterialApp] (see `main.dart`);
/// do not multiply sizes here or typography double-scales.
class IOSTextStyle {
  IOSTextStyle._();

  static TextTheme _textTheme(BuildContext context) =>
      Theme.of(context).textTheme;

  static Color _onSurface(BuildContext context) =>
      Theme.of(context).colorScheme.onSurface;

  /// Same curve as Material text scaling (for callers that need numeric scale only).
  static double getTextScaleFactor(BuildContext context) {
    return LayoutScale.screenScaleFactor(context);
  }

  static TextStyle largeTitle(BuildContext context) {
    return _textTheme(context).displayLarge!.copyWith(
          fontWeight: FontWeight.w700,
          letterSpacing: 0.37,
          color: _onSurface(context),
        );
  }

  static TextStyle title1(BuildContext context) {
    return _textTheme(context).displayMedium!.copyWith(
          fontWeight: FontWeight.w700,
          letterSpacing: 0.36,
          color: _onSurface(context),
        );
  }

  static TextStyle title2(BuildContext context) {
    return _textTheme(context).headlineSmall!.copyWith(
          fontWeight: FontWeight.w700,
          letterSpacing: 0.35,
          color: _onSurface(context),
        );
  }

  static TextStyle title3(BuildContext context) {
    return _textTheme(context).headlineMedium!.copyWith(
          letterSpacing: 0.38,
          color: _onSurface(context),
        );
  }

  static TextStyle headline(BuildContext context) {
    return _textTheme(context).bodyLarge!.copyWith(
          fontWeight: FontWeight.w600,
          letterSpacing: -0.41,
          color: _onSurface(context),
        );
  }

  static TextStyle body(BuildContext context) {
    return _textTheme(context).bodyLarge!.copyWith(
          fontWeight: FontWeight.w400,
          letterSpacing: -0.41,
          color: _onSurface(context),
        );
  }

  static TextStyle callout(BuildContext context) {
    return _textTheme(context).titleMedium!.copyWith(
          fontWeight: FontWeight.w400,
          letterSpacing: -0.32,
          color: _onSurface(context),
        );
  }

  static TextStyle subheadline(BuildContext context) {
    return _textTheme(context).bodyMedium!.copyWith(
          letterSpacing: -0.24,
          color: _onSurface(context),
        );
  }

  static TextStyle footnote(BuildContext context) {
    return _textTheme(context).labelMedium!.copyWith(
          fontWeight: FontWeight.w400,
          letterSpacing: -0.08,
          color: _onSurface(context).withValues(alpha: 0.6),
        );
  }

  static TextStyle caption1(BuildContext context) {
    return _textTheme(context).bodySmall!.copyWith(
          letterSpacing: 0,
          color: _onSurface(context).withValues(alpha: 0.6),
        );
  }

  static TextStyle caption2(BuildContext context) {
    return _textTheme(context).labelSmall!.copyWith(
          letterSpacing: 0.07,
          color: _onSurface(context).withValues(alpha: 0.6),
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
    return baseRadius * AppSpacing.getScaleFactor(context);
  }

  /// Context-aware border radius values
  static double borderRadiusSmallOf(BuildContext context) => scaledBorderRadius(context, borderRadiusSmall);
  static double borderRadiusMediumOf(BuildContext context) => scaledBorderRadius(context, borderRadiusMedium);
  static double borderRadiusLargeOf(BuildContext context) => scaledBorderRadius(context, borderRadiusLarge);
  static double borderRadiusXLargeOf(BuildContext context) => scaledBorderRadius(context, borderRadiusXLarge);
}
