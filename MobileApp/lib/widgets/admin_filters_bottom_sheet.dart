import 'dart:math' as math;

import 'package:flutter/material.dart';

/// Shows a scrollable admin filter sheet from the bottom of the screen.
///
/// Use with [AdminFilterPanel] (or any child) for consistent behavior:
/// keyboard-safe [AnimatedPadding], bottom safe area (nav bar / home indicator),
/// max height (92% of screen), drag handle,
/// and scroll when content is tall.
///
/// Overlay routes do not rebuild when the parent calls [State.setState]. Pass
/// [setModalState] from the [builder] together with [State.setState] when
/// switches, dropdowns, or other controls inside the sheet must update visually.
Future<T?> showAdminFiltersBottomSheet<T>({
  required BuildContext context,
  required Widget Function(
    BuildContext sheetContext,
    StateSetter setModalState,
  ) builder,
}) {
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: true,
    useSafeArea: true,
    showDragHandle: true,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (sheetContext) {
      return StatefulBuilder(
        builder: (context, setModalState) {
          final viewInsetsBottom = MediaQuery.viewInsetsOf(context).bottom;
          final viewPaddingBottom =
              MediaQuery.viewPaddingOf(context).bottom;
          // Keyboard (viewInsets) or system nav / home indicator (viewPadding);
          // do not sum — when the keyboard is open it dominates.
          final bottomPad =
              math.max(viewInsetsBottom, viewPaddingBottom);
          final maxSheetH = MediaQuery.sizeOf(context).height * 0.92;
          return AnimatedPadding(
            duration: const Duration(milliseconds: 150),
            curve: Curves.easeOutCubic,
            padding: EdgeInsets.only(bottom: bottomPad),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxHeight: maxSheetH),
              child: SingleChildScrollView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                child: builder(sheetContext, setModalState),
              ),
            ),
          );
        },
      );
    },
  );
}
