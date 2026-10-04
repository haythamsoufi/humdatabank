import 'package:flutter/material.dart';

/// Fixed colors for the grouped dashboard cards.
///
/// Kept out of `lib/screens` and `lib/widgets` so those layers stay on theme
/// tokens. The values are the light-mode card, hairline, status washes, and
/// avatar fills from the grouped layout.
abstract final class GroupedDashboardPalette {
  static const card = Color(0xFFFFFFFF);
  static const onFill = Color(0xFFFFFFFF);
  static const hairline = Color(0xFFE5E5EA);

  static const overdueWash = Color(0xFFFEE2E2);
  static const submitted = Color(0xFF15803D);
  static const submittedWash = Color(0xFFDCFCE7);
  static const muted = Color(0xFF6B7280);
  static const mutedDark = Color(0xFFD1D5DB);
  static const mutedWash = Color(0xFFF3F4F6);
  static const mutedWashDark = Color(0xFF374151);
  static const progressOnDark = Color(0xFFBFDBFE);
  static const amber = Color(0xFFB45309);
  static const amberWash = Color(0xFFFEF3C7);

  static const avatarColors = <Color>[
    Color(0xFF0F766E),
    Color(0xFFB45309),
    Color(0xFF011E41),
    Color(0xFF1D4ED8),
    Color(0xFF7C3AED),
    Color(0xFFBE123C),
    Color(0xFF0369A1),
    Color(0xFF3F6212),
  ];
}
