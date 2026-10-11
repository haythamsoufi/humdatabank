import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import 'grouped_dashboard_palette.dart';

/// Bottom sheets, filter chips, and option rows that follow the grouped
/// assignments dashboard: gray canvas, white (or elevated) cards, hairline
/// borders, and navy titles. Dark mode uses the same status wash as the cards.
abstract final class GroupedSheetStyle {
  static const double sheetRadius = 20;
  static const double cardRadius = 14;
  static const double chipRadius = 20;

  static bool isDark(ThemeData theme) => theme.brightness == Brightness.dark;

  static Color canvasFor({required bool isDark}) => isDark
      ? IOSColors.groupedTableViewBackgroundDark
      : IOSColors.groupedTableViewBackground;

  static Color canvasOf(ThemeData theme) => canvasFor(isDark: isDark(theme));

  static Color canvas(BuildContext context) => canvasOf(Theme.of(context));

  static Color cardFor({required bool isDark, required ColorScheme scheme}) =>
      isDark ? scheme.surfaceContainerHigh : GroupedDashboardPalette.card;

  static Color cardOf(ThemeData theme) =>
      cardFor(isDark: isDark(theme), scheme: theme.colorScheme);

  static Color card(BuildContext context) => cardOf(Theme.of(context));

  static Color hairlineFor({required bool isDark, required ColorScheme scheme}) =>
      isDark
      ? scheme.outlineVariant.withValues(alpha: 0.45)
      : GroupedDashboardPalette.hairline;

  static Color hairlineOf(ThemeData theme) =>
      hairlineFor(isDark: isDark(theme), scheme: theme.colorScheme);

  static Color hairline(BuildContext context) => hairlineOf(Theme.of(context));

  static Color titleColorFor({required bool isDark, required ColorScheme scheme}) =>
      isDark ? scheme.onSurface : const Color(AppConstants.defaultNavy);

  static Color titleColorOf(ThemeData theme) =>
      titleColorFor(isDark: isDark(theme), scheme: theme.colorScheme);

  static Color titleColor(BuildContext context) =>
      titleColorOf(Theme.of(context));

  static Color selectedFillOf(ThemeData theme) {
    final accent = GroupedDashboardPalette.info.accent;
    if (isDark(theme)) return accent.withValues(alpha: 0.22);
    return GroupedDashboardPalette.info.background;
  }

  static Color selectedFill(BuildContext context) =>
      selectedFillOf(Theme.of(context));

  static Color selectedBorderOf(ThemeData theme) {
    final accent = GroupedDashboardPalette.info.accent;
    if (isDark(theme)) return accent.withValues(alpha: 0.55);
    return GroupedDashboardPalette.info.border;
  }

  static Color selectedBorder(BuildContext context) =>
      selectedBorderOf(Theme.of(context));

  static Color selectedForegroundOf(ThemeData theme) {
    if (isDark(theme)) {
      return Color.lerp(
        GroupedDashboardPalette.info.accent,
        Colors.white,
        0.5,
      )!;
    }
    return GroupedDashboardPalette.info.foreground;
  }

  static Color selectedForeground(BuildContext context) =>
      selectedForegroundOf(Theme.of(context));

  static Color dragHandleFor({required bool isDark}) => isDark
      ? Colors.white.withValues(alpha: 0.28)
      : IOSColors.systemGray3;

  static TextStyle title(BuildContext context) {
    return Theme.of(context).textTheme.titleLarge!.copyWith(
      fontWeight: FontWeight.w700,
      letterSpacing: -0.4,
      color: titleColor(context),
    );
  }

  static TextStyle section(BuildContext context) {
    return IOSTextStyle.caption1(context).copyWith(
      fontWeight: FontWeight.w700,
      letterSpacing: 0.7,
      color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.48),
    );
  }

  static const ShapeBorder shape = RoundedRectangleBorder(
    borderRadius: BorderRadius.vertical(top: Radius.circular(sheetRadius)),
  );

  static BoxDecoration sheetDecoration(BuildContext context) => BoxDecoration(
    color: canvas(context),
    borderRadius: const BorderRadius.vertical(
      top: Radius.circular(sheetRadius),
    ),
  );

  static InputDecoration fieldDecoration(
    BuildContext context, {
    String? label,
    String? hint,
  }) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(cardRadius);
    final line = hairline(context);
    final scheme = theme.colorScheme;
    return InputDecoration(
      labelText: label,
      hintText: hint,
      filled: true,
      fillColor: card(context),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: scheme.error),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: scheme.error, width: 1.5),
      ),
    );
  }

  /// Input, button, switch, and segmented-control theme for sheet contents.
  static ThemeData controlsTheme(BuildContext context) {
    final base = Theme.of(context);
    final scheme = base.colorScheme;
    final radius = BorderRadius.circular(cardRadius);
    final title = titleColor(context);
    final line = hairline(context);
    final dark = isDark(base);
    final primaryFill = dark ? scheme.primary : const Color(AppConstants.defaultNavy);

    final input = InputDecorationTheme(
      filled: true,
      fillColor: card(context),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: line),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: line),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: scheme.primary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: scheme.error),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: scheme.error, width: 1.5),
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

    final filled = FilledButton.styleFrom(
      backgroundColor: primaryFill,
      foregroundColor: Colors.white,
      elevation: 0,
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      shape: RoundedRectangleBorder(borderRadius: radius),
      textStyle: base.textTheme.labelLarge?.copyWith(
        fontWeight: FontWeight.w600,
        color: Colors.white,
      ),
    );

    final outlined = OutlinedButton.styleFrom(
      foregroundColor: title,
      side: BorderSide(color: line),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      shape: RoundedRectangleBorder(borderRadius: radius),
      textStyle: base.textTheme.labelLarge?.copyWith(
        fontWeight: FontWeight.w600,
      ),
    );

    return base.copyWith(
      inputDecorationTheme: input,
      filledButtonTheme: FilledButtonThemeData(style: filled),
      outlinedButtonTheme: OutlinedButtonThemeData(style: outlined),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: title,
          textStyle: base.textTheme.labelLarge?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          visualDensity: VisualDensity.standard,
          backgroundColor: WidgetStateProperty.resolveWith((states) {
            if (states.contains(WidgetState.selected)) {
              return selectedFill(context);
            }
            return card(context);
          }),
          foregroundColor: WidgetStateProperty.resolveWith((states) {
            if (states.contains(WidgetState.selected)) {
              return selectedForeground(context);
            }
            return title.withValues(alpha: 0.75);
          }),
          side: WidgetStateProperty.resolveWith((states) {
            if (states.contains(WidgetState.selected)) {
              return BorderSide(color: selectedBorder(context));
            }
            return BorderSide(color: line);
          }),
          shape: WidgetStatePropertyAll(
            RoundedRectangleBorder(borderRadius: radius),
          ),
        ),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return Colors.white;
          return scheme.outline;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return primaryFill;
          return line;
        }),
        trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
      ),
    );
  }
}

class GroupedSheetDragHandle extends StatelessWidget {
  const GroupedSheetDragHandle({super.key});

  @override
  Widget build(BuildContext context) {
    final dark = GroupedSheetStyle.isDark(Theme.of(context));
    return Container(
      margin: const EdgeInsets.only(top: 10, bottom: 6),
      width: 36,
      height: 4,
      decoration: BoxDecoration(
        color: GroupedSheetStyle.dragHandleFor(isDark: dark),
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }
}

class GroupedSheetCloseButton extends StatelessWidget {
  const GroupedSheetCloseButton({
    super.key,
    required this.onPressed,
    required this.tooltip,
  });

  final VoidCallback onPressed;
  final String tooltip;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      tooltip: tooltip,
      onPressed: () {
        HapticFeedback.lightImpact();
        onPressed();
      },
      style: IconButton.styleFrom(
        backgroundColor: GroupedSheetStyle.card(context),
        foregroundColor: GroupedSheetStyle.titleColor(context),
        side: BorderSide(color: GroupedSheetStyle.hairline(context)),
        fixedSize: const Size(36, 36),
        minimumSize: const Size(36, 36),
        padding: EdgeInsets.zero,
        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
      ),
      icon: const Icon(Icons.close_rounded, size: 20),
    );
  }
}

class GroupedSheetSectionLabel extends StatelessWidget {
  const GroupedSheetSectionLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text.toUpperCase(), style: GroupedSheetStyle.section(context));
  }
}

/// One selectable row inside a sheet, styled like an assignment card.
class GroupedSheetOption extends StatelessWidget {
  const GroupedSheetOption({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.subtitle,
    this.leading,
  });

  final String label;
  final String? subtitle;
  final bool selected;
  final VoidCallback onTap;
  final Widget? leading;

  @override
  Widget build(BuildContext context) {
    final title = GroupedSheetStyle.titleColor(context);
    final foreground = selected
        ? GroupedSheetStyle.selectedForeground(context)
        : title;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: selected
            ? GroupedSheetStyle.selectedFill(context)
            : GroupedSheetStyle.card(context),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(GroupedSheetStyle.cardRadius),
          side: BorderSide(
            color: selected
                ? GroupedSheetStyle.selectedBorder(context)
                : GroupedSheetStyle.hairline(context),
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            HapticFeedback.selectionClick();
            onTap();
          },
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                if (leading != null) ...[
                  IconTheme(
                    data: IconThemeData(color: foreground, size: 20),
                    child: leading!,
                  ),
                  const SizedBox(width: 12),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: IOSTextStyle.callout(context).copyWith(
                          fontWeight: selected
                              ? FontWeight.w600
                              : FontWeight.w500,
                          color: foreground,
                          height: 1.25,
                        ),
                      ),
                      if (subtitle != null && subtitle!.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          subtitle!,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: IOSTextStyle.footnote(context).copyWith(
                            color: Theme.of(
                              context,
                            ).colorScheme.onSurface.withValues(alpha: 0.55),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (selected) ...[
                  const SizedBox(width: 8),
                  Icon(Icons.check_rounded, color: foreground, size: 20),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Pill used for dashboard filters and other compact pickers.
class GroupedFilterChip extends StatelessWidget {
  const GroupedFilterChip({
    super.key,
    required this.label,
    required this.onTap,
    this.selected = false,
    this.icon,
    this.showChevron = true,
  });

  final String label;
  final VoidCallback onTap;
  final bool selected;
  final IconData? icon;
  final bool showChevron;

  @override
  Widget build(BuildContext context) {
    final foreground = selected
        ? GroupedSheetStyle.selectedForeground(context)
        : GroupedSheetStyle.titleColor(context).withValues(alpha: 0.75);
    return Material(
      color: selected
          ? GroupedSheetStyle.selectedFill(context)
          : GroupedSheetStyle.card(context),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(GroupedSheetStyle.chipRadius),
        side: BorderSide(
          color: selected
              ? GroupedSheetStyle.selectedBorder(context)
              : GroupedSheetStyle.hairline(context),
        ),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () {
          HapticFeedback.selectionClick();
          onTap();
        },
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[
                Icon(icon, size: 14, color: foreground),
                const SizedBox(width: 6),
              ],
              Flexible(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: IOSTextStyle.footnote(context).copyWith(
                    fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                    color: foreground,
                  ),
                ),
              ),
              if (showChevron) ...[
                const SizedBox(width: 2),
                Icon(Icons.expand_more_rounded, size: 16, color: foreground),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// Apply / clear row used at the bottom of filter sheets.
class GroupedSheetActions extends StatelessWidget {
  const GroupedSheetActions({
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
          child: FilledButton(onPressed: onApply, child: Text(applyLabel)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton(onPressed: onClear, child: Text(clearLabel)),
        ),
      ],
    );
  }
}
