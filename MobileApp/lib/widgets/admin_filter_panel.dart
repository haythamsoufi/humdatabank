import 'package:flutter/material.dart';

import 'shared/elevated_list_card.dart';

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

    final inner = Padding(
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (surfaceCard)
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: scheme.primaryContainer.withValues(alpha: 0.65),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: scheme.primary.withValues(alpha: 0.45),
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(8),
                    child: Icon(
                      leadingIcon,
                      size: 20,
                      color: scheme.onPrimaryContainer,
                    ),
                  ),
                )
              else
                Icon(
                  leadingIcon,
                  size: 24,
                  color: scheme.primary,
                ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.15,
                          ),
                    ),
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
              color: scheme.outline.withValues(alpha: 0.45),
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
        data: _filterTheme(context),
        child: surfaceCard
            ? DecoratedBox(
                decoration: BoxDecoration(
                  color: elevatedListCardSurfaceColor(theme),
                  borderRadius: BorderRadius.circular(14),
                  border: Border.all(
                    color: scheme.outline.withValues(alpha: 0.55),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.18),
                      blurRadius: 10,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: inner,
              )
            : inner,
      ),
    );
  }

  ThemeData _filterTheme(BuildContext context) {
    final base = Theme.of(context);
    final scheme = base.colorScheme;
    final borderRadius = BorderRadius.circular(12);

    final input = InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface.withValues(alpha: 0.55),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      isDense: false,
      border: OutlineInputBorder(
        borderRadius: borderRadius,
        borderSide: BorderSide(
          color: scheme.outlineVariant.withValues(alpha: 0.55),
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: borderRadius,
        borderSide: BorderSide(
          color: scheme.outlineVariant.withValues(alpha: 0.45),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: borderRadius,
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: borderRadius,
        borderSide: BorderSide(color: scheme.error),
      ),
      labelStyle: base.textTheme.bodyMedium?.copyWith(
        color: scheme.onSurfaceVariant,
      ),
      floatingLabelStyle: WidgetStateTextStyle.resolveWith((states) {
        if (states.contains(WidgetState.focused)) {
          return TextStyle(color: scheme.primary, fontWeight: FontWeight.w600);
        }
        return TextStyle(color: scheme.onSurfaceVariant);
      }),
    );

    final filledBtn = FilledButton.styleFrom(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      elevation: 0,
    );

    final outlineBtn = OutlinedButton.styleFrom(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
    );

    return base.copyWith(
      inputDecorationTheme: input,
      filledButtonTheme: FilledButtonThemeData(style: filledBtn),
      outlinedButtonTheme: OutlinedButtonThemeData(style: outlineBtn),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) {
            return scheme.onSurface.withValues(alpha: 0.38);
          }
          if (states.contains(WidgetState.selected)) {
            return scheme.onPrimary;
          }
          return scheme.onSurfaceVariant;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.disabled)) {
            return scheme.onSurface.withValues(alpha: 0.12);
          }
          if (states.contains(WidgetState.selected)) {
            return scheme.primary;
          }
          return scheme.outline.withValues(alpha: 0.55);
        }),
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
    return Row(
      children: [
        Expanded(
          child: FilledButton(
            onPressed: onApply,
            child: Text(applyLabel),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton(
            onPressed: onClear,
            child: Text(clearLabel),
          ),
        ),
      ],
    );
  }
}
