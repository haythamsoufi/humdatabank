import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform;
import 'package:flutter/widgets.dart';

/// Single width-based scale for typography, iOS spacing, iOS text styles, and icons.
///
/// Matches the former [ResponsiveTypography.screenTextScaleFactor] curve (Android
/// platform tweak + clamp) so Material [textTheme] scaling stays stable while
/// layout and `IOSTextStyle` / `IOSSpacing` no longer use divergent min/max bands.
class LayoutScale {
  LayoutScale._();

  /// Reference logical width for scaling (slightly above common “medium” phones so
  /// typical devices sit at or slightly below 1.0 before the platform tweak).
  static const double baseWidth = 411.0;

  static const double _minScale = 0.92;
  /// Never **increase** font size above the theme baseline based on width alone —
  /// wide phones were getting up to +8% text size, which felt oversized.
  static const double _maxScale = 1.0;

  /// Clamped scale from logical width; used by theme text, iOS spacing, and iOS typography.
  static double screenScaleFactor(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final base = width / baseWidth;

    final platformAdjustment = switch (defaultTargetPlatform) {
      TargetPlatform.android => 0.96,
      TargetPlatform.iOS => 1.0,
      TargetPlatform.macOS => 1.0,
      TargetPlatform.windows => 1.0,
      TargetPlatform.linux => 1.0,
      TargetPlatform.fuchsia => 1.0,
    };

    final min =
        defaultTargetPlatform == TargetPlatform.android ? 0.88 : _minScale;
    final scale = base * platformAdjustment;
    return scale.clamp(min, _maxScale);
  }
}
