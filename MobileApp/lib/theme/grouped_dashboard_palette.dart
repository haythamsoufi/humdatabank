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

  /// Status variants mirror Backoffice `.status-label--*` (components.css) and
  /// `assignment_status_variant` so mobile and web show the same colour per status.
  static const neutral = GroupedStatusColors(
    foreground: Color(0xFF475569),
    background: Color(0xFFF8FAFC),
    border: Color(0xFFCBD5E1),
    accent: Color(0xFF94A3B8),
  );
  static const success = GroupedStatusColors(
    foreground: Color(0xFF166534),
    background: Color(0xFFF0FDF4),
    border: Color(0xFF86EFAC),
    accent: Color(0xFF16A34A),
  );
  static const danger = GroupedStatusColors(
    foreground: Color(0xFF991B1B),
    background: Color(0xFFFEF2F2),
    border: Color(0xFFFCA5A5),
    accent: Color(0xFFEF4444),
  );
  static const warning = GroupedStatusColors(
    foreground: Color(0xFF9A3412),
    background: Color(0xFFFFF7ED),
    border: Color(0xFFFDBA74),
    accent: Color(0xFFF97316),
  );
  static const review = GroupedStatusColors(
    foreground: Color(0xFF6B21A8),
    background: Color(0xFFFAF5FF),
    border: Color(0xFFD8B4FE),
    accent: Color(0xFF9333EA),
  );
  static const pending = GroupedStatusColors(
    foreground: Color(0xFF854D0E),
    background: Color(0xFFFFFBEB),
    border: Color(0xFFFCD34D),
    accent: Color(0xFFF59E0B),
  );
  static const info = GroupedStatusColors(
    foreground: Color(0xFF1E40AF),
    background: Color(0xFFEFF6FF),
    border: Color(0xFF93C5FD),
    accent: Color(0xFF3B82F6),
  );

  static const mailAction = Color(0xFF011E41);
  static const teamsAction = Color(0xFF5B5FC7);

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

/// Foreground, wash, border, and edge accent for one status variant.
class GroupedStatusColors {
  const GroupedStatusColors({
    required this.foreground,
    required this.background,
    required this.border,
    required this.accent,
  });

  final Color foreground;
  final Color background;
  final Color border;
  final Color accent;
}
