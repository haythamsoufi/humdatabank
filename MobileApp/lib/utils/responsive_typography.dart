import 'package:flutter/foundation.dart' show TargetPlatform, defaultTargetPlatform;
import 'package:flutter/widgets.dart';

/// Centralized typography scaling helpers.
///
/// Important:
/// - This is meant to adjust typography slightly based on *screen size*.
/// - It does NOT replace OS accessibility text scaling; Flutter will still apply
///   the system text scale factor on top of the theme text styles.
class ResponsiveTypography {
  // Base design width (iPhone 12/13/14 logical width)
  static const double _baseWidth = 390.0;

  // Clamp to avoid extreme scaling on very small / very large devices.
  static const double _minScale = 0.92;
  static const double _maxScale = 1.08;

  /// Returns a small, clamped scaling factor based on current screen width.
  static double screenTextScaleFactor(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final base = width / _baseWidth;

    // Montserrat tends to render a bit larger on Android compared to iOS.
    // Also, many Android devices ship with slightly larger default text/display
    // scaling. Apply a small platform adjustment so the UI feels consistent.
    final platformAdjustment = switch (defaultTargetPlatform) {
      TargetPlatform.android => 0.96,
      TargetPlatform.iOS => 1.0,
      TargetPlatform.macOS => 1.0,
      TargetPlatform.windows => 1.0,
      TargetPlatform.linux => 1.0,
      TargetPlatform.fuchsia => 1.0,
    };

    final min = defaultTargetPlatform == TargetPlatform.android ? 0.88 : _minScale;
    final scale = base * platformAdjustment;
    return scale.clamp(min, _maxScale);
  }
}
