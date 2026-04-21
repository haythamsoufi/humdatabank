import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;

import 'app_spacing.dart';
import 'ios_constants.dart';
import 'theme_extensions.dart';

/// Centralized layout, typography, and chrome for iOS-style settings / grouped lists.
/// Use across screens that should match the Settings visual language.
abstract final class IOSSettingsStyle {
  IOSSettingsStyle._();

  /// Large navigation title + sliver scroll on iPhone; Material app bar elsewhere.
  static bool get useIosSettingsChrome =>
      defaultTargetPlatform == TargetPlatform.iOS;

  static const double leadingIconSize = 22;

  static const double chevronTrailingSize = 13;

  static const double chevronTrailingOpacity = 0.3;

  /// Space between grouped sections on settings-style pages.
  static double get sectionSpacing => AppSpacing.xxl;

  /// Vertical padding for grouped list rows on iPhone (≈44pt row height with body text).
  static EdgeInsets get listRowContentPadding {
    if (useIosSettingsChrome) {
      return const EdgeInsets.symmetric(
        horizontal: IOSSpacing.md,
        vertical: 12,
      );
    }
    return const EdgeInsets.symmetric(
      horizontal: IOSSpacing.md,
      vertical: IOSSpacing.sm,
    );
  }

  /// Horizontal inset for full-width controls (e.g. grouped buttons) and cards.
  static double get pageHorizontalInset => AppSpacing.md;

  static const double groupedPlainButtonMinHeight = 48;

  static const EdgeInsets groupedPlainButtonPadding =
      EdgeInsets.symmetric(vertical: 14);

  /// Scroll physics for settings-style pages (bouncing on iOS when using sliver body).
  static ScrollPhysics pageScrollPhysics({bool alwaysScrollable = true}) {
    if (useIosSettingsChrome) {
      return BouncingScrollPhysics(
        parent: alwaysScrollable ? const AlwaysScrollableScrollPhysics() : null,
      );
    }
    return alwaysScrollable
        ? const AlwaysScrollableScrollPhysics()
        : const ClampingScrollPhysics();
  }

  static Color groupedTableBackground(BuildContext context) =>
      IOSColors.getGroupedBackground(context);

  static Color secondaryCellBackground(BuildContext context) {
    final theme = Theme.of(context);
    return theme.isDarkTheme
        ? IOSColors.secondarySystemBackgroundDark
        : IOSColors.secondarySystemBackground;
  }

  static TextStyle rowTitleStyle(BuildContext context) {
    return IOSTextStyle.body(context).copyWith(
      fontWeight: FontWeight.w400,
      color: Theme.of(context).colorScheme.onSurface,
    );
  }

  static TextStyle rowSubtitleStyle(BuildContext context) {
    return IOSTextStyle.callout(context).copyWith(
      color: Theme.of(context).colorScheme.onSurface.withValues(
            alpha: 0.6,
          ),
    );
  }

  /// Small label above a grouped table (matches [IOSGroupedList] headers).
  static TextStyle sectionHeaderStyle(BuildContext context) {
    final theme = Theme.of(context);
    return IOSTextStyle.footnote(context).copyWith(
      fontWeight: FontWeight.w600,
      color: theme.colorScheme.onSurface.withValues(alpha: 0.55),
      letterSpacing: 0.2,
    );
  }

  static Color switchActiveTrackColor(BuildContext context) =>
      IOSColors.getSystemBlue(context);

  /// Leading glyph for settings rows (Cupertino-style).
  static Widget leadingIcon(
    BuildContext context,
    IconData icon, {
    Color? color,
    double? size,
  }) {
    return Icon(
      icon,
      size: size ?? leadingIconSize,
      color: color ?? Theme.of(context).colorScheme.onSurface,
    );
  }

  /// Trailing chevron for navigation rows.
  static Widget disclosureChevron(BuildContext context) {
    return Icon(
      cupertino.CupertinoIcons.chevron_right,
      size: chevronTrailingSize,
      color: Theme.of(context).colorScheme.onSurface.withValues(
            alpha: chevronTrailingOpacity,
          ),
    );
  }

  /// Bottom border for [cupertino.CupertinoSliverNavigationBar].
  static Border navigationBarBottomBorder(BuildContext context) {
    return Border(
      bottom: BorderSide(
        color: cupertino.CupertinoColors.separator.resolveFrom(context),
        width: 0.5,
      ),
    );
  }
}
