import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Border color for [ElevatedListCard] (outline blended onto surface).
Color elevatedListCardBorderColor(ColorScheme scheme, Color surfaceBlend) {
  return Color.alphaBlend(
    scheme.outline.withValues(alpha: 0.35),
    surfaceBlend,
  );
}

/// Surface fill for bordered list cards: white in light theme, elevated
/// container tint in dark. Use with [elevatedListCardBorderColor] when building
/// custom [Material] / [DecoratedBox] shells that match [ElevatedListCard].
Color elevatedListCardSurfaceColor(ThemeData theme) {
  final scheme = theme.colorScheme;
  return theme.brightness == Brightness.light
      ? Colors.white
      : scheme.surfaceContainerHighest.withValues(alpha: 0.65);
}

/// Bordered, lightly filled list row (grouped-card look).
class ElevatedListCard extends StatelessWidget {
  const ElevatedListCard({
    super.key,
    required this.child,
    this.marginBottom = 10,
    this.padding = const EdgeInsets.fromLTRB(14, 12, 14, 12),
  });

  final Widget child;
  final double marginBottom;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final surfaceColor = elevatedListCardSurfaceColor(theme);
    final borderColor = elevatedListCardBorderColor(scheme, surfaceColor);

    return Padding(
      padding: EdgeInsets.only(bottom: marginBottom),
      child: Material(
        color: surfaceColor,
        elevation: 0,
        shadowColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: borderColor, width: 1),
        ),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: padding,
          child: child,
        ),
      ),
    );
  }
}

/// Compact label + value chip for list rows.
class ListMetricChip extends StatelessWidget {
  const ListMetricChip({
    super.key,
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHigh.withValues(alpha: 0.85),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: scheme.outlineVariant.withValues(alpha: 0.35),
        ),
      ),
      child: Text.rich(
        TextSpan(
          children: [
            if (label.isNotEmpty)
              TextSpan(
                text: '$label ',
                style: textTheme.labelSmall?.copyWith(
                  color: scheme.onSurfaceVariant,
                  fontWeight: FontWeight.w500,
                ),
              ),
            TextSpan(
              text: value,
              style: textTheme.labelLarge?.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: 0.2,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Divider + gap before footer actions (session log tiles, assignment cards).
class ListCardFooterActions extends StatelessWidget {
  const ListCardFooterActions({
    super.key,
    required this.child,
  });

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 10),
          child: Divider(
            height: 1,
            thickness: 1,
            color: scheme.outlineVariant.withValues(alpha: 0.45),
          ),
        ),
        const SizedBox(height: 6),
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
