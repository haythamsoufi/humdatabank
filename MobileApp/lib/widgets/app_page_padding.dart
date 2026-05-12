import 'package:flutter/material.dart';

import '../utils/app_spacing.dart';

/// Standard horizontal inset for scrollable page content (matches settings page inset).
class AppPagePadding extends StatelessWidget {
  const AppPagePadding({
    super.key,
    required this.child,
    this.horizontal,
    this.vertical,
  });

  final Widget child;

  /// Defaults to [AppSpacing.md] (16) before [LayoutScale].
  final double? horizontal;

  final double? vertical;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: AppSpacing.symmetric(
        context,
        horizontal: horizontal ?? AppSpacing.md,
        vertical: vertical ?? 0,
      ),
      child: child,
    );
  }
}
