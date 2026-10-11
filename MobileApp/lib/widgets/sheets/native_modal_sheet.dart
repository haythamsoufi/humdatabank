import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../theme/grouped_sheet_style.dart';

/// Drag handle matching the grouped assignments dashboard sheets.
class NativeModalSheetDragHandle extends StatelessWidget {
  const NativeModalSheetDragHandle({super.key});

  @override
  Widget build(BuildContext context) {
    return const GroupedSheetDragHandle();
  }
}

/// Rounded sheet from the bottom: handle, title row + close, divider, body.
///
/// Use with [showModalBottomSheet] and `backgroundColor: Colors.transparent`,
/// `isScrollControlled: true` — same pattern as [HomeScreen] country picker.
///
/// When [bodyExpands] is `true` (default), the body is in an [Expanded] and
/// fills remaining height (e.g. long lists). When `false`, the sheet only grows
/// to fit the body up to the max height — use with a [ScrollView] that has
/// `shrinkWrap: true` so short content does not leave a large blank region.
class NativeModalSheetScaffold extends StatelessWidget {
  const NativeModalSheetScaffold({
    super.key,
    required this.theme,
    required this.title,
    required this.closeTooltip,
    required this.onClose,
    required this.child,
    this.maxHeightFraction = 0.9,
    this.bodyExpands = true,
  });

  final ThemeData theme;
  final String title;
  final String closeTooltip;
  final VoidCallback onClose;
  final Widget child;
  final double maxHeightFraction;

  /// When `true`, body fills all space below the header (typical for lists).
  /// When `false`, body height follows content until [maxHeightFraction] cap.
  final bool bodyExpands;

  /// Handle + title row + divider — used to size the scrollable region when
  /// [bodyExpands] is `false`.
  static const double _chromeHeightEstimate = 126;

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: theme,
      child: Builder(
        builder: (context) {
          return Theme(
            data: GroupedSheetStyle.controlsTheme(context),
            child: Container(
              constraints: BoxConstraints(
                maxHeight: MediaQuery.sizeOf(context).height * maxHeightFraction,
              ),
              decoration: GroupedSheetStyle.sheetDecoration(context),
              child: SafeArea(
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    final bodyMax = math.max(
                      120.0,
                      constraints.maxHeight - _chromeHeightEstimate,
                    );
                    return Column(
                      mainAxisSize: bodyExpands
                          ? MainAxisSize.max
                          : MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Align(
                          alignment: Alignment.center,
                          child: NativeModalSheetDragHandle(),
                        ),
                        Padding(
                          padding: const EdgeInsets.fromLTRB(20, 4, 12, 10),
                          child: Row(
                            children: [
                              Expanded(
                                child: Text(
                                  title,
                                  style: GroupedSheetStyle.title(context),
                                ),
                              ),
                              GroupedSheetCloseButton(
                                onPressed: onClose,
                                tooltip: closeTooltip,
                              ),
                            ],
                          ),
                        ),
                        Divider(
                          height: 1,
                          thickness: 1,
                          color: GroupedSheetStyle.hairline(context),
                        ),
                        if (bodyExpands)
                          Expanded(child: child)
                        else
                          ConstrainedBox(
                            constraints: BoxConstraints(maxHeight: bodyMax),
                            child: child,
                          ),
                      ],
                    );
                  },
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

/// One labeled choice in [showGroupedOptionPicker].
class GroupedPickerChoice {
  const GroupedPickerChoice({
    required this.label,
    required this.selected,
    required this.onSelected,
  });

  final String label;
  final bool selected;
  final VoidCallback onSelected;
}

/// Scrollable option list in the grouped sheet chrome.
Future<void> showGroupedOptionPicker({
  required BuildContext context,
  required String title,
  required String closeTooltip,
  required List<GroupedPickerChoice> choices,
  double maxHeightFraction = 0.72,
}) async {
  if (choices.isEmpty) return;
  final theme = Theme.of(context);
  await showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (sheetContext) {
      return NativeModalSheetScaffold(
        theme: theme,
        title: title,
        closeTooltip: closeTooltip,
        maxHeightFraction: maxHeightFraction,
        onClose: () => Navigator.pop(sheetContext),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
          children: [
            for (final choice in choices)
              GroupedSheetOption(
                label: choice.label,
                selected: choice.selected,
                onTap: () {
                  Navigator.pop(sheetContext);
                  choice.onSelected();
                },
              ),
          ],
        ),
      );
    },
  );
}

/// FDRS reporting period list in the shared native sheet chrome.
Future<void> showReportingPeriodPickerSheet({
  required BuildContext context,
  required AppLocalizations l10n,
  required List<String> periods,
  required String selectedPeriod,
  required ValueChanged<String> onSelected,
  double maxHeightFraction = 0.55,
}) async {
  if (periods.isEmpty) return;
  final theme = Theme.of(context);
  await showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.transparent,
    isScrollControlled: true,
    builder: (bottomSheetContext) {
      return NativeModalSheetScaffold(
        theme: theme,
        title: l10n.homeLandingGlobalPeriodFilterLabel,
        closeTooltip: l10n.close,
        maxHeightFraction: maxHeightFraction,
        onClose: () => Navigator.pop(bottomSheetContext),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
          children: [
            for (final p in periods)
              GroupedSheetOption(
                label: p,
                selected: p == selectedPeriod,
                onTap: () {
                  onSelected(p);
                  Navigator.pop(bottomSheetContext);
                },
              ),
          ],
        ),
      );
    },
  );
}

/// Tappable row (underline style) that opens [showReportingPeriodPickerSheet].
///
/// Hidden when [periods] is empty or has a single entry (nothing to pick).
class ReportingPeriodPickerField extends StatelessWidget {
  const ReportingPeriodPickerField({
    super.key,
    required this.l10n,
    required this.periods,
    required this.value,
    required this.onChanged,
    this.compact = false,
  });

  final AppLocalizations l10n;
  final List<String> periods;
  final String? value;
  final ValueChanged<String?> onChanged;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (periods.isEmpty || periods.length <= 1) {
      return const SizedBox.shrink();
    }
    final theme = Theme.of(context);
    final effective = value != null && periods.contains(value)
        ? value!
        : periods.first;
    return Semantics(
      button: true,
      label: l10n.homeLandingGlobalPeriodFilterLabel,
      value: effective,
      child: Material(
        color: GroupedSheetStyle.card(context),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(GroupedSheetStyle.cardRadius),
          side: BorderSide(color: GroupedSheetStyle.hairline(context)),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () {
            HapticFeedback.selectionClick();
            showReportingPeriodPickerSheet(
              context: context,
              l10n: l10n,
              periods: periods,
              selectedPeriod: effective,
              onSelected: (p) => onChanged(p),
            );
          },
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: 14,
              vertical: compact ? 8 : 10,
            ),
            child: Row(
              children: [
                Icon(
                  Icons.calendar_today_rounded,
                  size: 18,
                  color: GroupedSheetStyle.titleColor(context),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        l10n.homeLandingGlobalPeriodFilterLabel,
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        effective,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: GroupedSheetStyle.titleColor(context),
                          fontWeight: FontWeight.w600,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.keyboard_arrow_down_rounded,
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
