import 'package:flutter/widgets.dart';

import 'layout_scale.dart';

/// Canonical spacing scale for Material screens, iOS chrome, and list padding.
///
/// Use fixed constants for layout that should not grow with [LayoutScale], or
/// [scaled] / `*Of` helpers when matching typography responsive scaling.
abstract final class AppSpacing {
  AppSpacing._();

  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 16.0;
  static const double lg = 20.0;
  static const double xl = 24.0;
  static const double xxl = 32.0;

  /// Same curve as [MaterialApp] text scaling in `main.dart`.
  static double getScaleFactor(BuildContext context) {
    return LayoutScale.screenScaleFactor(context);
  }

  static double scaled(BuildContext context, double baseValue) {
    return baseValue * getScaleFactor(context);
  }

  static double xsOf(BuildContext context) => scaled(context, xs);
  static double smOf(BuildContext context) => scaled(context, sm);
  static double mdOf(BuildContext context) => scaled(context, md);
  static double lgOf(BuildContext context) => scaled(context, lg);
  static double xlOf(BuildContext context) => scaled(context, xl);
  static double xxlOf(BuildContext context) => scaled(context, xxl);

  static EdgeInsets all(BuildContext context, double value) {
    return EdgeInsets.all(scaled(context, value));
  }

  static EdgeInsets symmetric(
    BuildContext context, {
    double? horizontal,
    double? vertical,
  }) {
    return EdgeInsets.symmetric(
      horizontal: horizontal != null ? scaled(context, horizontal) : 0,
      vertical: vertical != null ? scaled(context, vertical) : 0,
    );
  }

  static EdgeInsets only(
    BuildContext context, {
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

  static EdgeInsets fromLTRB(
    BuildContext context,
    double left,
    double top,
    double right,
    double bottom,
  ) {
    return EdgeInsets.fromLTRB(
      scaled(context, left),
      scaled(context, top),
      scaled(context, right),
      scaled(context, bottom),
    );
  }
}
