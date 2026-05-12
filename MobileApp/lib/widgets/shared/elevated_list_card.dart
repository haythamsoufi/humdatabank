import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';

/// Surface fill for bordered list cards: white in light theme, elevated
/// container tint in dark.
Color elevatedListCardSurfaceColor(ThemeData theme) {
  final scheme = theme.colorScheme;
  return theme.brightness == Brightness.light
      ? Colors.white
      : scheme.surfaceContainerHighest.withValues(alpha: 0.65);
}

/// Lightly filled list row (grouped-card look).
class ElevatedListCard extends StatelessWidget {
  const ElevatedListCard({
    super.key,
    required this.child,
    this.marginBottom = 10,
    this.padding = const EdgeInsets.fromLTRB(14, 12, 14, 12),
    this.borderRadius = 12,
    this.outlineColor,
    this.backgroundColor,
    this.boxShadow,
  });

  final Widget child;
  final double marginBottom;
  final EdgeInsetsGeometry padding;
  final double borderRadius;
  /// Optional hairline border (e.g. [ColorScheme.outlineVariant]) for definition on grouped backgrounds.
  final Color? outlineColor;
  /// When set, replaces the default elevated surface (e.g. overdue tint on assignment cards).
  final Color? backgroundColor;
  /// Soft outer glow (e.g. red halo for overdue). Drawn outside [Material] so radius matches the card.
  final List<BoxShadow>? boxShadow;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final surfaceColor =
        backgroundColor ?? elevatedListCardSurfaceColor(theme);
    final side = outlineColor != null
        ? BorderSide(color: outlineColor!, width: 0.5)
        : BorderSide.none;

    final radius = BorderRadius.circular(borderRadius);
    Widget material = Material(
      color: surfaceColor,
      elevation: 0,
      shadowColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: radius,
        side: side,
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: padding,
        child: child,
      ),
    );

    final shadows = boxShadow;
    if (shadows != null && shadows.isNotEmpty) {
      material = DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: radius,
          boxShadow: shadows,
        ),
        child: material,
      );
    }

    return Padding(
      padding: EdgeInsets.only(bottom: marginBottom),
      child: material,
    );
  }
}

/// Semantic styling for [ListMetricChip] (completion vs due date).
enum ListMetricChipVariant {
  neutral,
  completion,
  dueDate,
  /// No due date set — lower contrast than [dueDate].
  dueDateMissing,
}

/// Label + value on one line (wraps when narrow), with a left accent stripe.
class ListMetricChip extends StatelessWidget {
  const ListMetricChip({
    super.key,
    required this.label,
    required this.value,
    this.variant = ListMetricChipVariant.neutral,
    this.valueSuffix,
    /// When [variant] is [completion], drives stripe/fill/value (default: success green).
    this.completionAccent,
  });

  final String label;
  final String value;
  final ListMetricChipVariant variant;
  /// Shown beside [value] (e.g. “Overdue” in error colour when past due).
  final String? valueSuffix;
  final Color? completionAccent;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final brightness = theme.brightness;
    final suffix = valueSuffix;

    final Color accent;
    final Color fill;
    final Color frame;
    final Color valueColor;

    switch (variant) {
      case ListMetricChipVariant.completion:
        accent = completionAccent ?? const Color(AppConstants.successColor);
        fill = accent.withValues(alpha: brightness == Brightness.dark ? 0.16 : 0.09);
        frame = accent.withValues(alpha: brightness == Brightness.dark ? 0.42 : 0.28);
        valueColor = accent;
      case ListMetricChipVariant.dueDate:
        accent = IOSColors.getSystemBlue(context);
        fill = accent.withValues(alpha: brightness == Brightness.dark ? 0.18 : 0.09);
        frame = accent.withValues(alpha: brightness == Brightness.dark ? 0.45 : 0.28);
        valueColor = accent;
      case ListMetricChipVariant.dueDateMissing:
        accent = scheme.outlineVariant.withValues(alpha: 0.9);
        fill = scheme.surfaceContainerHighest.withValues(alpha: brightness == Brightness.dark ? 0.35 : 0.65);
        frame = scheme.outlineVariant.withValues(alpha: 0.32);
        valueColor = scheme.onSurfaceVariant.withValues(alpha: 0.72);
      case ListMetricChipVariant.neutral:
        accent = scheme.outline;
        fill = scheme.surfaceContainerHigh.withValues(alpha: 0.88);
        frame = scheme.outlineVariant.withValues(alpha: 0.45);
        valueColor = scheme.onSurface;
    }

    final bool mutedDue = variant == ListMetricChipVariant.dueDateMissing;
    final TextStyle? valueTextStyle = mutedDue
        ? theme.textTheme.bodySmall?.copyWith(
            fontWeight: FontWeight.w500,
            letterSpacing: 0.05,
            height: 1.2,
            color: valueColor,
          )
        : theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
            letterSpacing: 0.1,
            height: 1.15,
            color: valueColor,
          );

    return Container(
      constraints: const BoxConstraints(minWidth: 0),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(10),
        // Uniform border color so [borderRadius] is valid (Flutter forbids mixed colors + radius).
        border: Border.all(color: frame, width: 0.5),
      ),
      clipBehavior: Clip.antiAlias,
      child: Stack(
        clipBehavior: Clip.hardEdge,
        children: [
          Positioned(
            left: 0,
            top: 0,
            bottom: 0,
            width: 3,
            child: ColoredBox(color: accent),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 8, 12, 8),
            child: Wrap(
              spacing: 6,
              runSpacing: 2,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                if (label.isNotEmpty)
                  Text(
                    label,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: mutedDue
                          ? scheme.onSurfaceVariant.withValues(alpha: 0.65)
                          : scheme.onSurfaceVariant,
                      fontWeight: mutedDue ? FontWeight.w500 : FontWeight.w600,
                      letterSpacing: mutedDue ? 0.25 : 0.35,
                      height: 1.1,
                    ),
                  ),
                Text(
                  value,
                  style: valueTextStyle,
                ),
                if (suffix != null && suffix.isNotEmpty)
                  Text(
                    suffix,
                    style: mutedDue
                        ? theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.15,
                            height: 1.2,
                            color: scheme.error.withValues(alpha: 0.85),
                          )
                        : theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.2,
                            height: 1.15,
                            color: scheme.error,
                          ),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Divider + gap before footer actions (session log tiles, assignment cards).
class ListCardFooterActions extends StatelessWidget {
  const ListCardFooterActions({
    super.key,
    required this.child,
    this.dividerTopPadding = 10,
    this.gapAfterDivider = 6,
  });

  final Widget child;
  /// Space above the hairline (smaller values tighten the footer block).
  final double dividerTopPadding;
  /// Space between divider and [child].
  final double gapAfterDivider;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: EdgeInsets.only(top: dividerTopPadding),
          child: Divider(
            height: 1,
            thickness: 1,
            color: scheme.outlineVariant.withValues(alpha: 0.45),
          ),
        ),
        SizedBox(height: gapAfterDivider),
        child,
      ],
    );
  }
}

typedef FlipListFooterBuilder = Widget? Function(
  BuildContext context,
  Animation<double> flipAnimation,
);

/// Exposes [toggleFlip] to [front] / [back] children (e.g. explicit flip-back control).
class FlipListCardScope extends InheritedWidget {
  const FlipListCardScope({
    super.key,
    required this.toggleFlip,
    required super.child,
  });

  final VoidCallback toggleFlip;

  static FlipListCardScope? maybeOf(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<FlipListCardScope>();
  }

  static FlipListCardScope of(BuildContext context) {
    final scope = maybeOf(context);
    assert(scope != null, 'FlipListCardScope not found');
    return scope!;
  }

  @override
  bool updateShouldNotify(FlipListCardScope oldWidget) => false;
}

/// Y-axis flip between [front] and [back] with optional trailing/footer.
///
/// [frontBuilder] and [backBuilder] receive a [BuildContext] below [FlipListCardScope]
/// so children can call [FlipListCardScope.of] (e.g. flip controls).
class FlipListCard extends StatefulWidget {
  const FlipListCard({
    super.key,
    required this.frontBuilder,
    required this.backBuilder,
    this.trailingWhenFront,
    this.footerBuilder,
  });

  final Widget Function(BuildContext context) frontBuilder;
  final Widget Function(BuildContext context) backBuilder;
  final Widget? trailingWhenFront;
  final FlipListFooterBuilder? footerBuilder;

  @override
  State<FlipListCard> createState() => _FlipListCardState();
}

class _FlipListCardState extends State<FlipListCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _flipController;
  late Animation<double> _flipAnimation;

  @override
  void initState() {
    super.initState();
    _flipController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
    );
    _flipAnimation = CurvedAnimation(
      parent: _flipController,
      curve: Curves.easeInOutCubic,
    );
  }

  @override
  void dispose() {
    _flipController.dispose();
    super.dispose();
  }

  void _toggleFlip() {
    if (_flipController.isCompleted) {
      _flipController.reverse();
    } else {
      _flipController.forward();
    }
  }

  @override
  Widget build(BuildContext context) {
    return FlipListCardScope(
      toggleFlip: _toggleFlip,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: _toggleFlip,
                  behavior: HitTestBehavior.opaque,
                  child: AnimatedBuilder(
                    animation: _flipAnimation,
                    builder: (context, _) {
                      final angle = _flipAnimation.value * math.pi;
                      return Transform(
                        transform: Matrix4.identity()
                          ..setEntry(3, 2, 0.001)
                          ..rotateY(angle),
                        alignment: Alignment.center,
                        child: angle <= math.pi / 2
                            ? Builder(
                                builder: (ctx) =>
                                    widget.frontBuilder(ctx),
                              )
                            : Transform(
                                transform: Matrix4.identity()
                                  ..rotateY(math.pi),
                                alignment: Alignment.center,
                                child: Builder(
                                  builder: (ctx) =>
                                      widget.backBuilder(ctx),
                                ),
                              ),
                      );
                    },
                  ),
                ),
              ),
              if (widget.trailingWhenFront != null)
                AnimatedBuilder(
                  animation: _flipAnimation,
                  builder: (context, _) {
                    if (_flipAnimation.value < 0.5) {
                      return widget.trailingWhenFront!;
                    }
                    return const SizedBox(width: 48);
                  },
                ),
            ],
          ),
          if (widget.footerBuilder != null)
            AnimatedBuilder(
              animation: _flipAnimation,
              builder: (context, _) {
                return widget.footerBuilder!(context, _flipAnimation) ??
                    const SizedBox.shrink();
              },
            ),
        ],
      ),
    );
  }
}
