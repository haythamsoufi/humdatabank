import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

/// Minimum touch target size per WCAG 2.5.5 (Level AAA) and Material guidelines.
/// Android/Material: 48x48 dp, iOS HIG: 44x44 pt.
class AccessibilityConstants {
  AccessibilityConstants._();

  static const double minTouchTarget = 48.0;
  static const Size minTouchTargetSize = Size(minTouchTarget, minTouchTarget);

  static const double minContrastRatioNormal = 4.5;
  static const double minContrastRatioLarge = 3.0;

  static const Duration minAnimationDuration = Duration(milliseconds: 100);
  static const Duration toastDuration = Duration(seconds: 4);

  /// Focus order groups for screen readers.
  static const int focusOrderHeader = 0;
  static const int focusOrderContent = 1;
  static const int focusOrderActions = 2;
  static const int focusOrderNavigation = 3;
}

/// Wraps a widget to ensure minimum touch target size.
class AccessibleTapTarget extends StatelessWidget {
  final Widget child;
  final VoidCallback? onTap;
  final String? semanticLabel;
  final String? semanticHint;
  final double minSize;

  const AccessibleTapTarget({
    super.key,
    required this.child,
    this.onTap,
    this.semanticLabel,
    this.semanticHint,
    this.minSize = AccessibilityConstants.minTouchTarget,
  });

  @override
  Widget build(BuildContext context) {
    Widget result = ConstrainedBox(
      constraints: BoxConstraints(
        minWidth: minSize,
        minHeight: minSize,
      ),
      child: child,
    );

    if (onTap != null) {
      result = InkWell(
        onTap: onTap,
        child: result,
      );
    }

    if (semanticLabel != null || semanticHint != null) {
      result = Semantics(
        label: semanticLabel,
        hint: semanticHint,
        button: onTap != null,
        child: result,
      );
    }

    return result;
  }
}

/// Announces a message to screen readers.
void announceToScreenReader(BuildContext context, String message) {
  SemanticsService.sendAnnouncement(View.of(context), message, Directionality.of(context));
}
