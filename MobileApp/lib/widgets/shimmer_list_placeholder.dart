import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

import '../utils/constants.dart';

/// Standardized skeleton loader: a vertical list of shimmering placeholder
/// rows that approximate the shape of items being loaded.
///
/// Use as a drop-in replacement for full-screen [CircularProgressIndicator]
/// when loading a list (assignments, users, resources, templates, …). The
/// shimmer base/highlight colours come from [AppConstants.semanticShimmer*]
/// so light/dark themes stay coherent.
class ShimmerListPlaceholder extends StatelessWidget {
  const ShimmerListPlaceholder({
    super.key,
    this.itemCount = 6,
    this.itemBuilder,
    this.padding = const EdgeInsets.fromLTRB(16, 16, 16, 16),
    this.itemSpacing = 12,
    this.physics,
  });

  final int itemCount;

  /// Optional builder for the placeholder shape; defaults to
  /// [ShimmerCardPlaceholder] which works for most list rows.
  final WidgetBuilder? itemBuilder;

  final EdgeInsets padding;
  final double itemSpacing;
  final ScrollPhysics? physics;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final base = isDark
        ? const Color(AppConstants.semanticShimmerBaseDark)
        : const Color(AppConstants.semanticShimmerBaseLight);
    final highlight = isDark
        ? const Color(AppConstants.semanticShimmerHighlightDark)
        : const Color(AppConstants.semanticShimmerHighlightLight);

    return Shimmer.fromColors(
      baseColor: base,
      highlightColor: highlight,
      period: const Duration(milliseconds: 1400),
      child: ListView.separated(
        padding: padding,
        physics: physics ?? const NeverScrollableScrollPhysics(),
        itemCount: itemCount,
        separatorBuilder: (_, _) => SizedBox(height: itemSpacing),
        itemBuilder: (context, _) =>
            itemBuilder?.call(context) ?? const ShimmerCardPlaceholder(),
      ),
    );
  }
}

/// A generic card-shaped shimmer block: leading circle, two text lines,
/// and a small trailing chip. Suitable for most list rows in the app.
class ShimmerCardPlaceholder extends StatelessWidget {
  const ShimmerCardPlaceholder({
    super.key,
    this.height = 84,
    this.borderRadius = 12,
  });

  final double height;
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: height,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(borderRadius),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: const BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  height: 12,
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  height: 10,
                  width: 140,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(4),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Container(
            width: 56,
            height: 22,
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(11),
            ),
          ),
        ],
      ),
    );
  }
}

/// Compact tile shimmer used for grid / dashboard stat cards.
class ShimmerTilePlaceholder extends StatelessWidget {
  const ShimmerTilePlaceholder({
    super.key,
    this.height = 110,
    this.borderRadius = 14,
  });

  final double height;
  final double borderRadius;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final base = isDark
        ? const Color(AppConstants.semanticShimmerBaseDark)
        : const Color(AppConstants.semanticShimmerBaseLight);
    final highlight = isDark
        ? const Color(AppConstants.semanticShimmerHighlightDark)
        : const Color(AppConstants.semanticShimmerHighlightLight);

    return Shimmer.fromColors(
      baseColor: base,
      highlightColor: highlight,
      period: const Duration(milliseconds: 1400),
      child: Container(
        height: height,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(borderRadius),
        ),
      ),
    );
  }
}
