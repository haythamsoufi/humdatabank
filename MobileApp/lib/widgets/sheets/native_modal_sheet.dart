import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../utils/ios_constants.dart';
import '../ios_button.dart';

/// Drag handle matching [HomeScreen] / resources / disaggregation bottom sheets.
class NativeModalSheetDragHandle extends StatelessWidget {
  const NativeModalSheetDragHandle({super.key, required this.theme});

  final ThemeData theme;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(
        top: IOSSpacing.md - 4,
        bottom: IOSSpacing.sm,
      ),
      width: 40,
      height: 4,
      decoration: BoxDecoration(
        color: theme.dividerColor,
        borderRadius: BorderRadius.circular(2),
      ),
    );
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
    return Container(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * maxHeightFraction,
      ),
      decoration: BoxDecoration(
        color: theme.scaffoldBackgroundColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final bodyMax = math.max(
              120.0,
              constraints.maxHeight - _chromeHeightEstimate,
            );
            return Column(
              mainAxisSize: bodyExpands ? MainAxisSize.max : MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: Alignment.center,
                  child: NativeModalSheetDragHandle(theme: theme),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: IOSSpacing.xl,
                    vertical: IOSSpacing.md,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Expanded(
                        child: Text(
                          title,
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                      ),
                      IOSIconButton(
                        icon: Icons.close,
                        onPressed: onClose,
                        tooltip: closeTooltip,
                        semanticLabel: closeTooltip,
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
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
    );
  }
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
        child: ListView.separated(
          padding: const EdgeInsets.only(bottom: 16),
          itemCount: periods.length,
          separatorBuilder: (_, _) => Divider(
            height: 1,
            thickness: 1,
            color: theme.dividerColor.withValues(alpha: 0.35),
          ),
          itemBuilder: (context, index) {
            final p = periods[index];
            final selected = p == selectedPeriod;
            return ListTile(
              title: Text(
                p,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
              trailing: selected
                  ? Icon(
                      Icons.check,
                      color: theme.colorScheme.secondary,
                    )
                  : null,
              onTap: () {
                HapticFeedback.selectionClick();
                onSelected(p);
                Navigator.pop(bottomSheetContext);
              },
            );
          },
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
    final effective =
        value != null && periods.contains(value) ? value! : periods.first;
    final isDark = theme.brightness == Brightness.dark;
    final line = theme.colorScheme.outlineVariant
        .withValues(alpha: isDark ? 0.5 : 0.38);

    final topPad = compact ? 4.0 : 8.0;
    final bottomPad = compact ? 8.0 : 10.0;

    return Semantics(
      button: true,
      label: l10n.homeLandingGlobalPeriodFilterLabel,
      value: effective,
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
          padding: EdgeInsets.only(top: topPad, bottom: bottomPad),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                l10n.homeLandingGlobalPeriodFilterLabel,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
              SizedBox(height: compact ? 2 : 4),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      effective,
                      style: (compact
                              ? theme.textTheme.bodyMedium
                              : theme.textTheme.bodyLarge)
                          ?.copyWith(
                        color: theme.colorScheme.onSurface,
                        fontWeight: FontWeight.w500,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  Icon(
                    Icons.keyboard_arrow_down_rounded,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ],
              ),
              SizedBox(height: compact ? 6 : 8),
              Divider(height: 1, thickness: 1, color: line),
            ],
          ),
        ),
      ),
    );
  }
}
