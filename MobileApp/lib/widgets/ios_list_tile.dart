import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import '../utils/ios_constants.dart';
import '../utils/ios_settings_style.dart';
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
    final isDark = theme.isDarkTheme;

    final bgColor = backgroundColor ??
        (isDark
            ? IOSColors.secondarySystemBackgroundDark
            : IOSColors.secondarySystemBackground);

    Widget content = Container(
      color: bgColor,
      padding: contentPadding ?? IOSSettingsStyle.listRowContentPadding,
      child: Row(
        children: [
          if (leading != null) ...[
            leading!,
            const SizedBox(width: IOSSpacing.md),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                ?title,
                if (subtitle != null) ...[
                  const SizedBox(height: IOSSpacing.xs / 2),
                  subtitle!,
                ],
              ],
            ),
          ),
          if (trailing != null) ...[
            const SizedBox(width: IOSSpacing.sm),
            trailing!,
          ],
        ],
      ),
    );

    if (onTap != null) {
      content = cupertino.CupertinoButton(
        padding: EdgeInsets.zero,
        color: Colors.transparent,
        onPressed: onTap,
        minimumSize: Size.zero,
        child: content,
      );
    }

    // Separator is handled by IOSGroupedList, so we don't add it here
    return content;
  }
}

/// Settings row with a [CupertinoSwitch] and shared [IOSSettingsStyle] typography.
class IOSListSwitchTile extends StatelessWidget {
  const IOSListSwitchTile({
    super.key,
    required this.leading,
    required this.title,
    this.subtitle,
    required this.value,
    required this.onChanged,
    required this.semanticsLabel,
    this.enabled = true,
  });

  final IconData leading;
  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final String semanticsLabel;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: semanticsLabel,
      value: value ? 'On' : 'Off',
      toggled: value,
      enabled: enabled,
      child: IOSListTile(
        leading: IOSSettingsStyle.leadingIcon(context, leading),
        title: Text(
          title,
          style: IOSSettingsStyle.rowTitleStyle(context),
        ),
        subtitle: subtitle != null
            ? Text(
                subtitle!,
                style: IOSSettingsStyle.rowSubtitleStyle(context),
              )
            : null,
        trailing: cupertino.CupertinoSwitch(
          value: value,
          onChanged: enabled ? onChanged : null,
          activeTrackColor: IOSSettingsStyle.switchActiveTrackColor(context),
        ),
      ),
    );
  }
}

/// iOS-style grouped list section (like iOS Settings app)
class IOSGroupedList extends StatelessWidget {
  final List<Widget> children;
  final Widget? header;
  final String? headerText;
  final String? footer;
  final EdgeInsetsGeometry? margin;

  const IOSGroupedList({
    super.key,
    required this.children,
    this.header,
    this.headerText,
    this.footer,
    this.margin,
  }) : assert(header == null || headerText == null,
            'Provide either header or headerText, not both');

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.isDarkTheme;

    final bgColor = isDark
        ? IOSColors.secondarySystemBackgroundDark
        : IOSColors.secondarySystemBackground;

    final separatorColor = IOSSettingsStyle.useIosSettingsChrome
        ? cupertino.CupertinoColors.separator.resolveFrom(context)
        : theme.dividerColor;

    // Build items with separators (except last one)
    // iOS uses subtle separators between items
    final List<Widget> itemsWithSeparators = [];
    for (int i = 0; i < children.length; i++) {
      final child = children[i];

      // Calculate left margin for separator based on whether child has leading icon
      double separatorLeftMargin = IOSSpacing.md;
      if (child is IOSListTile && child.leading != null) {
        separatorLeftMargin =
            IOSSpacing.md * 2 + IOSSettingsStyle.leadingIconSize;
      } else if (child is IOSListSwitchTile) {
        separatorLeftMargin =
            IOSSpacing.md * 2 + IOSSettingsStyle.leadingIconSize;
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

    final effectiveHeader = header ??
        (headerText != null
            ? Text(
                headerText!,
                style: IOSTextStyle.footnote(context).copyWith(
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                ),
              )
            : null);

    // iOS Settings–style inset groups: visibly rounded card; clip row backgrounds
    // to the curve (Material tiles do not respect parent radius without clipping).
    final double groupCornerRadius = IOSSettingsStyle.useIosSettingsChrome
        ? IOSDimensions.borderRadiusLargeOf(context)
        : IOSDimensions.borderRadiusMediumOf(context);
    // Light theme: inset card without outer stroke (matches iOS Settings groups).
    final Border? groupBorder = IOSSettingsStyle.useIosSettingsChrome && isDark
        ? Border.all(
            color: cupertino.CupertinoColors.separator
                .resolveFrom(context)
                .withValues(alpha: 0.4),
            width: 0.5,
          )
        : null;

    return Container(
      margin: margin ?? const EdgeInsets.only(bottom: IOSSpacing.xl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (effectiveHeader != null)
            Padding(
              padding: const EdgeInsets.only(
                left: IOSSpacing.md,
                right: IOSSpacing.md,
                bottom: IOSSpacing.sm,
                top: IOSSpacing.sm,
              ),
              child: effectiveHeader,
            ),
          Container(
            decoration: BoxDecoration(
              color: bgColor,
              borderRadius: BorderRadius.circular(groupCornerRadius),
              border: groupBorder,
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(groupCornerRadius),
              clipBehavior: Clip.antiAlias,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: itemsWithSeparators,
              ),
            ),
          ),
          if (footer != null)
            Padding(
              padding: const EdgeInsets.only(
                left: IOSSpacing.md,
                right: IOSSpacing.md,
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
