import 'dart:ui' show ImageFilter;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';


/// A circular bubble of glass that hosts a header icon.
///
/// On iOS the bubble is the same system material as the floating tab bar
/// (Liquid Glass on iOS 26, the ultra-thin blur earlier). That platform view
/// is a capsule, so a square box renders as a circle. Other platforms use a
/// Flutter [BackdropFilter] approximation.
///
/// [child] is centered in a [size] square. `IconButton`s are resized to fill
/// the bubble so the whole circle is the tap target.
class GlassCircleBubble extends StatelessWidget {
  /// Diameter of the bubble.
  static const double defaultSize = 40;

  /// iOS platform view registered in `AppDelegate`.
  static const String _systemGlassViewType = 'hum_databank/glass_capsule';

  final Widget child;
  final double size;

  const GlassCircleBubble({
    super.key,
    required this.child,
    this.size = defaultSize,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final cs = theme.colorScheme;

    final useSystemGlass =
        !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

    final Widget surface;
    if (useSystemGlass) {
      surface = IgnorePointer(
        child: UiKitView(
          key: ValueKey<bool>(isDark),
          viewType: _systemGlassViewType,
          creationParams: <String, Object>{'dark': isDark},
          creationParamsCodec: const StandardMessageCodec(),
          gestureRecognizers: const <Factory<OneSequenceGestureRecognizer>>{},
          hitTestBehavior: PlatformViewHitTestBehavior.transparent,
        ),
      );
    } else {
      final fillTop = isDark
          ? Colors.white.withValues(alpha: 0.16)
          : Colors.white.withValues(alpha: 0.85);
      final fillBottom = isDark
          ? Colors.white.withValues(alpha: 0.06)
          : Colors.white.withValues(alpha: 0.5);
      final hairline = isDark
          ? cs.outlineVariant.withValues(alpha: 0.7)
          : Colors.white.withValues(alpha: 0.9);
      surface = DecoratedBox(
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.4 : 0.08),
              blurRadius: 12,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: ClipOval(
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 18, sigmaY: 18),
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [fillTop, fillBottom],
                ),
                border: Border.all(
                  color: hairline,
                  width: 0.6,
                  strokeAlign: BorderSide.strokeAlignInside,
                ),
              ),
            ),
          ),
        ),
      );
    }

    return SizedBox.square(
      dimension: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Positioned.fill(child: surface),
          Theme(
            data: theme.copyWith(
              iconButtonTheme: IconButtonThemeData(
                style: IconButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(size),
                  fixedSize: Size.square(size),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  shape: const CircleBorder(),
                ),
              ),
            ),
            child: child,
          ),
        ],
      ),
    );
  }
}

/// Icon button inside a [GlassCircleBubble], used for header back, menu and
/// action buttons.
class GlassCircleButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback? onPressed;
  final String? tooltip;
  final Color? color;
  final double iconSize;

  const GlassCircleButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.tooltip,
    this.color,
    this.iconSize = 22,
  });

  @override
  Widget build(BuildContext context) {
    final iconColor = color ?? Theme.of(context).colorScheme.onSurface;
    return GlassCircleBubble(
      child: IconButton(
        tooltip: tooltip,
        icon: Icon(icon, size: iconSize, color: iconColor),
        onPressed: onPressed == null
            ? null
            : () {
                HapticFeedback.lightImpact();
                onPressed!();
              },
      ),
    );
  }
}
