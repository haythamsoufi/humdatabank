import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../utils/constants.dart';

/// Animated check icon for success confirmations (form save, action done).
///
/// Renders a circular badge that scales/elastics in, followed by a faint
/// pulse. Pair with a snackbar or success state body for celebratory UX.
class AnimatedSuccessCheck extends StatelessWidget {
  const AnimatedSuccessCheck({
    super.key,
    this.size = 64,
    this.color,
  });

  final double size;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final accent = color ?? const Color(AppConstants.successColor);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.12),
        shape: BoxShape.circle,
      ),
      child: Icon(
        Icons.check_rounded,
        size: size * 0.55,
        color: accent,
      ),
    )
        .animate()
        .scale(
          begin: const Offset(0.4, 0.4),
          end: const Offset(1.0, 1.0),
          duration: 360.ms,
          curve: Curves.elasticOut,
        )
        .fadeIn(duration: 200.ms)
        .then(delay: 120.ms)
        .shimmer(duration: 600.ms, color: accent.withValues(alpha: 0.35));
  }
}
