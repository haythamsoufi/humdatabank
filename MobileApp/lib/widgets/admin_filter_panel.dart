import 'package:flutter/material.dart';

import '../theme/grouped_sheet_style.dart';

/// Shared filter pane: optional card-style surface, themed inputs, and optional Apply/Clear row.
/// Use inline, under [AnimatedCrossFade], or inside `showAdminFiltersBottomSheet` from
/// `admin_filters_bottom_sheet.dart`; wrap fields in [child] and pass the same [title]
/// string you use for the app bar filter tooltip.
class AdminFilterPanel extends StatelessWidget {
  const AdminFilterPanel({
    super.key,
    required this.title,
    this.subtitle,
    this.leadingIcon = Icons.tune_rounded,
    this.actions,
    this.padding = const EdgeInsets.fromLTRB(16, 8, 16, 12),
    this.showHeaderDivider = true,
    this.surfaceCard = true,
    required this.child,
  });

  final String title;
  final String? subtitle;
  final IconData leadingIcon;
  final Widget? actions;

  /// Outer padding around the card (screen edge insets).
  final EdgeInsets padding;

  final bool showHeaderDivider;

  /// When `true` (default), draws the rounded surface, border, and shadow.
  /// Set to `false` for bottom sheets where the sheet already provides a surface.
  final bool surfaceCard;

  final Widget child;

  /// Vertical gap between stacked fields inside [child].
  static const Widget fieldGap = SizedBox(height: 12);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final accent = GroupedSheetStyle.selectedForeground(context);

    final inner = Padding(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DecoratedBox(
                decoration: BoxDecoration(
                  color: GroupedSheetStyle.selectedFill(context),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: GroupedSheetStyle.selectedBorder(context),
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(8),
                  child: Icon(leadingIcon, size: 20, color: accent),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: GroupedSheetStyle.title(context)),
                    if (subtitle != null && subtitle!.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        subtitle!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                          height: 1.25,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
          if (showHeaderDivider) ...[
            const SizedBox(height: 12),
            Divider(
              height: 1,
              thickness: 1,
              color: GroupedSheetStyle.hairline(context),
            ),
            const SizedBox(height: 12),
          ] else
            const SizedBox(height: 12),
          child,
          if (actions != null) ...[
            const SizedBox(height: 12),
            actions!,
          ],
        ],
      ),
    );

    return Padding(
      padding: padding,
      child: Theme(
        data: GroupedSheetStyle.controlsTheme(context),
        child: surfaceCard
            ? DecoratedBox(
                decoration: BoxDecoration(
                  color: GroupedSheetStyle.card(context),
                  borderRadius: BorderRadius.circular(
                    GroupedSheetStyle.cardRadius,
                  ),
                  border: Border.all(color: GroupedSheetStyle.hairline(context)),
                ),
                child: inner,
              )
            : inner,
      ),
    );
  }
}

/// Primary + secondary actions for filter panels (typically Apply / Clear).
class AdminFilterPanelActions extends StatelessWidget {
  const AdminFilterPanelActions({
    super.key,
    required this.applyLabel,
    required this.clearLabel,
    required this.onApply,
    required this.onClear,
  });

  final String applyLabel;
  final String clearLabel;
  final VoidCallback onApply;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return GroupedSheetActions(
      applyLabel: applyLabel,
      clearLabel: clearLabel,
      onApply: onApply,
      onClear: onClear,
    );
  }
}
