import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';

/// iOS-native list tile that matches iOS Settings app appearance
class IOSListTile extends StatelessWidget {
  final Widget? leading;
  final Widget? title;
  final Widget? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;
  final Color? backgroundColor;
  final bool showSeparator; // Deprecated - separators handled by IOSGroupedList
  final EdgeInsetsGeometry? contentPadding;

  const IOSListTile({
    super.key,
    this.leading,
    this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
    this.backgroundColor,
    this.showSeparator = true,
    this.contentPadding,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final bgColor = backgroundColor ??
        (isDark
            ? IOSColors.secondarySystemBackgroundDark
            : IOSColors.secondarySystemBackground);

    final separatorColor = isDark
        ? Colors.white.withOpacity(0.1)
        : Colors.black.withOpacity(0.1);

    Widget content = Container(
      color: bgColor,
      padding: contentPadding ?? EdgeInsets.symmetric(
        horizontal: IOSSpacing.md,
        vertical: IOSSpacing.sm,
      ),
      child: Row(
        children: [
          if (leading != null) ...[
            leading!,
            SizedBox(width: IOSSpacing.md),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                if (title != null) title!,
                if (subtitle != null) ...[
                  SizedBox(height: IOSSpacing.xs / 2),
                  subtitle!,
                ],
              ],
            ),
          ),
          if (trailing != null) ...[
            SizedBox(width: IOSSpacing.sm),
            trailing!,
          ],
        ],
      ),
    );

    if (onTap != null) {
      content = cupertino.CupertinoButton(
        padding: EdgeInsets.zero,
        minSize: 0,
        color: Colors.transparent,
        onPressed: onTap,
        child: content,
      );
    }

    // Separator is handled by IOSGroupedList, so we don't add it here
    return content;
  }
}

/// iOS-style grouped list section (like iOS Settings app)
class IOSGroupedList extends StatelessWidget {
  final List<Widget> children;
  final Widget? header;
  final String? footer;
  final EdgeInsetsGeometry? margin;

  const IOSGroupedList({
    super.key,
    required this.children,
    this.header,
    this.footer,
    this.margin,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    final bgColor = isDark
        ? IOSColors.secondarySystemBackgroundDark
        : IOSColors.secondarySystemBackground;

    final separatorColor = isDark
        ? Colors.white.withOpacity(0.1)
        : Colors.black.withOpacity(0.1);

    // Build items with separators (except last one)
    // iOS uses subtle separators between items
    final List<Widget> itemsWithSeparators = [];
    for (int i = 0; i < children.length; i++) {
      final child = children[i];

      // Calculate left margin for separator based on whether child has leading icon
      double separatorLeftMargin = IOSSpacing.md;
      if (child is IOSListTile && child.leading != null) {
        separatorLeftMargin = IOSSpacing.md * 2 + 20; // icon width + spacing
      }

      itemsWithSeparators.add(child);
      if (i < children.length - 1) {
        itemsWithSeparators.add(
          Container(
            height: 0.5,
            margin: EdgeInsets.only(left: separatorLeftMargin),
            color: separatorColor,
          ),
        );
      }
    }

    return Container(
      margin: margin ?? EdgeInsets.only(bottom: IOSSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (header != null)
            Padding(
              padding: EdgeInsets.only(
                left: IOSSpacing.xl,
                right: IOSSpacing.xl,
                bottom: IOSSpacing.sm,
                top: IOSSpacing.sm,
              ),
              child: header is String
                  ? Text(
                      header as String,
                      style: IOSTextStyle.footnote(context).copyWith(
                        fontWeight: FontWeight.w600,
                        color: theme.colorScheme.onSurface.withOpacity(0.6),
                      ),
                    )
                  : header!,
            ),
          Container(
            decoration: BoxDecoration(
              color: bgColor,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              children: itemsWithSeparators,
            ),
          ),
          if (footer != null)
            Padding(
              padding: EdgeInsets.only(
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
