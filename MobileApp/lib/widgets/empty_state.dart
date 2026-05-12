import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../utils/constants.dart';

/// Standardized animated empty-state widget for screens that have no data
/// to display. Renders a circular badge with an icon, a primary headline,
/// and an optional subtitle line — all entering with a brief, polished
/// scale + fade choreography (similar to Lottie illustrations but without
/// the asset overhead).
///
/// Use as a drop-in replacement for ad-hoc Center+Column empty states
/// across list screens (assignments, users, notifications, …).
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.icon,
    required this.title,
    this.subtitle,
    this.action,
    this.iconColor,
    this.iconSize = 64,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget? action;
  final Color? iconColor;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = iconColor ?? theme.colorScheme.primary;
    final secondary = theme.colorScheme.onSurface.withValues(alpha: 0.6);

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: iconSize + 32,
              height: iconSize + 32,
              decoration: BoxDecoration(
                color: accent.withValues(alpha: 0.10),
                shape: BoxShape.circle,
              ),
              child: Icon(
                icon,
                size: iconSize,
                color: accent.withValues(alpha: 0.9),
              ),
            )
                .animate()
                .scale(
                  begin: const Offset(0.6, 0.6),
                  end: const Offset(1.0, 1.0),
                  duration: 420.ms,
                  curve: Curves.elasticOut,
                )
                .fadeIn(duration: 220.ms)
                .then(delay: 1200.ms)
                .moveY(
                  begin: 0,
                  end: -6,
                  duration: 1800.ms,
                  curve: Curves.easeInOut,
                )
                .then()
                .moveY(
                  begin: -6,
                  end: 0,
                  duration: 1800.ms,
                  curve: Curves.easeInOut,
                ),
            const SizedBox(height: 20),
            Text(
              title,
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                color: theme.colorScheme.onSurface,
              ),
            )
                .animate()
                .fadeIn(delay: 180.ms, duration: 260.ms)
                .moveY(begin: 8, end: 0, duration: 260.ms, curve: Curves.easeOut),
            if (subtitle != null) ...[
              const SizedBox(height: 6),
              Text(
                subtitle!,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium?.copyWith(color: secondary),
              )
                  .animate()
                  .fadeIn(delay: 280.ms, duration: 260.ms)
                  .moveY(
                    begin: 8,
                    end: 0,
                    duration: 260.ms,
                    curve: Curves.easeOut,
                  ),
            ],
            if (action != null) ...[
              const SizedBox(height: 24),
              action!
                  .animate()
                  .fadeIn(delay: 380.ms, duration: 260.ms)
                  .moveY(
                    begin: 10,
                    end: 0,
                    duration: 260.ms,
                    curve: Curves.easeOut,
                  ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Shorthand: empty state coloured to use the brand red accent (errors / no
/// matches), useful when a list of important data unexpectedly came back empty.
class AppEmptyStateBrand extends AppEmptyState {
  AppEmptyStateBrand({
    super.key,
    required super.icon,
    required super.title,
    super.subtitle,
    super.action,
  }) : super(iconColor: Color(AppConstants.ifrcRed));
}
