import 'package:flutter/material.dart';
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';

/// iOS-style card widget for consistent card design across the app
class IOSCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final Color? backgroundColor;
  final VoidCallback? onTap;
  final bool useGroupedStyle;

  const IOSCard({
    super.key,
    required this.child,
    this.padding,
    this.margin,
    this.backgroundColor,
    this.onTap,
    this.useGroupedStyle = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    // iOS grouped table view style - no background, just container
    if (useGroupedStyle) {
      return Container(
        margin: margin ?? EdgeInsets.zero,
        child: child,
      );
    }

    // Standard iOS card style - no shadows, just clean background
    final cardColor = backgroundColor ??
        (isDark
            ? IOSColors.secondarySystemBackgroundDark
            : IOSColors.secondarySystemBackground);

    return Container(
      margin: margin ?? EdgeInsets.zero,
      decoration: BoxDecoration(
        color: cardColor,
        borderRadius: BorderRadius.circular(10), // iOS uses 10px for grouped lists
      ),
      child: onTap != null
          ? Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: onTap,
                borderRadius: BorderRadius.circular(10),
                child: Padding(
                  padding: padding ?? EdgeInsets.zero,
                  child: child,
                ),
              ),
            )
          : Padding(
              padding: padding ?? EdgeInsets.zero,
              child: child,
            ),
    );
  }
}

/// iOS-style grouped section widget
class IOSGroupedSection extends StatelessWidget {
  final List<Widget> children;
  final String? header;
  final String? footer;
  final EdgeInsetsGeometry? margin;

  const IOSGroupedSection({
    super.key,
    required this.children,
    this.header,
    this.footer,
    this.margin,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Container(
      margin: margin ?? const EdgeInsets.only(bottom: IOSSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (header != null)
            Padding(
              padding: const EdgeInsets.only(
                left: IOSSpacing.xl,
                right: IOSSpacing.xl,
                bottom: IOSSpacing.sm,
              ),
              child: Text(
                header!,
                style: IOSTextStyle.footnote(context).copyWith(
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurface.withOpacity(0.6),
                ),
              ),
            ),
          Container(
            decoration: BoxDecoration(
              color: IOSColors.getGroupedBackground(context),
              borderRadius: BorderRadius.circular(10), // iOS uses 10px
            ),
            child: Column(
              children: children,
            ),
          ),
          if (footer != null)
            Padding(
              padding: const EdgeInsets.only(
                left: IOSSpacing.xl,
                right: IOSSpacing.xl,
                top: IOSSpacing.sm,
              ),
              child: Text(
                footer!,
                style: IOSTextStyle.caption1(context),
              ),
            ),
        ],
      ),
    );
  }
}
