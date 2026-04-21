import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import '../utils/constants.dart';
import '../utils/theme_extensions.dart';

/// Parses `#RRGGBB` / `RRGGBB` / `AARRGGBB` for profile disks (aligned with notifications).
Color? parseProfileColorHex(String? hex) {
  if (hex == null || hex.isEmpty) return null;
  var s = hex.trim();
  if (s.startsWith('#')) s = s.substring(1);
  if (s.length == 6) s = 'FF$s';
  if (s.length != 8) return null;
  try {
    return Color(int.parse(s, radix: 16));
  } catch (_) {
    return null;
  }
}

/// Icon-only leading (no actor): bordered surface circle + FA icon — notifications fallback row.
class ProfileLeadingIconFallback extends StatelessWidget {
  const ProfileLeadingIconFallback({
    super.key,
    required this.icon,
    required this.iconColor,
    this.size = 44,
    this.opacity,
  });

  final IconData icon;
  final Color iconColor;
  final double size;
  final double? opacity;

  static double _iconSize(double size) => size * 18 / 44;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget child = Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainerHighest
            .withValues(alpha: context.isDarkTheme ? 0.35 : 0.85),
        shape: BoxShape.circle,
        border: Border.all(
          color: theme.dividerColor,
          width: 0.5,
        ),
      ),
      child: Center(
        child: FaIcon(
          icon,
          size: _iconSize(size),
          color: iconColor,
        ),
      ),
    );
    if (opacity != null && opacity! < 1.0) {
      child = Opacity(opacity: opacity!, child: child);
    }
    return child;
  }
}

/// Standard profile / notification leading: solid (or optional gradient) disk + optional FA badge.
class ProfileLeadingAvatar extends StatelessWidget {
  const ProfileLeadingAvatar({
    super.key,
    required this.initials,
    this.profileColorHex,
    this.backgroundColor,
    this.badgeIcon,
    this.size = 44,
    this.opacity,
    this.useGradient = false,
    this.initialsColor,
    /// When true, the colored disk fills the [size] square (hero / banner). When false,
    /// uses notification list proportions (smaller disk + offset for badge alignment).
    this.fillSlot = false,
  });

  final String initials;
  final String? profileColorHex;
  final Color? backgroundColor;
  final IconData? badgeIcon;
  final double size;
  final double? opacity;
  final bool useGradient;
  /// When set (e.g. hero banner), overrides default white initials.
  final Color? initialsColor;
  final bool fillSlot;

  static double _rLeading(double size) => size * 18 / 44;
  static double _fontSizeLeading(double size) => size * 13 / 44;
  static double _badgeSize(double size) => size * 18 / 44;
  static double _badgeIconSize(double size) => size * 9 / 44;
  static double _topOffset(double size) => size * 2 / 44;

  Color _resolveBgColor() {
    if (backgroundColor != null) return backgroundColor!;
    return parseProfileColorHex(profileColorHex) ??
        const Color(AppConstants.semanticDefaultProfileAccent);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bg = _resolveBgColor();
    final fg = initialsColor ?? Colors.white;
    final useFill = fillSlot && badgeIcon == null;
    final r = useFill ? size / 2 : _rLeading(size);
    final fontSize =
        useFill ? size * 0.31 : _fontSizeLeading(size);
    final initialsDisk = Container(
      width: 2 * r,
      height: 2 * r,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: useGradient
            ? LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  bg,
                  bg.withValues(alpha: 0.8),
                ],
              )
            : null,
        color: useGradient ? null : bg,
      ),
      child: Center(
        child: Text(
          initials,
          style: TextStyle(
            color: fg,
            fontSize: fontSize,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );

    Widget child;
    if (badgeIcon != null) {
      final bs = _badgeSize(size);
      child = SizedBox(
        width: size,
        height: size,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned(
              left: 0,
              top: _topOffset(size),
              child: initialsDisk,
            ),
            Positioned(
              right: 0,
              bottom: 0,
              child: Container(
                width: bs,
                height: bs,
                decoration: BoxDecoration(
                  color: theme.colorScheme.surface,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: theme.dividerColor,
                    width: 0.5,
                  ),
                ),
                child: Center(
                  child: FaIcon(
                    badgeIcon,
                    size: _badgeIconSize(size),
                    color: theme.textTheme.bodySmall?.color,
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    } else if (useFill) {
      child = SizedBox(
        width: size,
        height: size,
        child: Center(child: initialsDisk),
      );
    } else {
      child = SizedBox(
        width: size,
        height: size,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Positioned(
              left: 0,
              top: _topOffset(size),
              child: initialsDisk,
            ),
          ],
        ),
      );
    }

    if (opacity != null && opacity! < 1.0) {
      return Opacity(opacity: opacity!, child: child);
    }
    return child;
  }
}
