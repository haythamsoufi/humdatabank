import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../utils/constants.dart';
import '../utils/ios_constants.dart';

/// Screen header shared by every page.
///
/// Matches the Dashboard heading: a large, left-aligned bold title on the
/// page background with no divider line. Back, menu and action icons are plain
/// `IconButton`s beside the title.
class AppAppBar extends StatelessWidget implements PreferredSizeWidget {
  /// Height of the header below the status bar.
  static const double toolbarHeight = 64;

  /// Horizontal inset, same as the Dashboard heading.
  static const double horizontalPadding = 20;

  /// Large heading text. An empty title leaves only the leading and action icons.
  final String title;
  final List<Widget>? actions;
  final Widget? leading;
  final bool automaticallyImplyLeading;

  /// Defaults to transparent so the header shows the Scaffold's own background.
  final Color? backgroundColor;

  const AppAppBar({
    super.key,
    required this.title,
    this.actions,
    this.leading,
    this.automaticallyImplyLeading = true,
    this.backgroundColor,
  });

  Widget? _resolveLeading(BuildContext context) {
    if (leading != null) return leading;
    if (!automaticallyImplyLeading) return null;

    final scaffold = Scaffold.maybeOf(context);
    if (Navigator.canPop(context)) {
      return IconButton(
        icon: const Icon(Icons.arrow_back_ios_new_rounded, size: 20),
        tooltip: MaterialLocalizations.of(context).backButtonTooltip,
        onPressed: () => Navigator.maybePop(context),
      );
    }
    if (scaffold != null && scaffold.hasDrawer) {
      return IconButton(
        icon: const Icon(Icons.menu_rounded),
        tooltip: MaterialLocalizations.of(context).openAppDrawerTooltip,
        onPressed: scaffold.openDrawer,
      );
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final titleColor = isDark
        ? theme.colorScheme.onSurface
        : const Color(AppConstants.defaultNavy);
    final leadingWidget = _resolveLeading(context);

    final titleStyle = IOSTextStyle.largeTitle(context).copyWith(
      fontWeight: FontWeight.w700,
      letterSpacing: -0.6,
      color: titleColor,
    );

    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: isDark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
      child: Material(
        color: backgroundColor ?? Colors.transparent,
        child: SafeArea(
          bottom: false,
          child: SizedBox(
            height: toolbarHeight,
            child: Padding(
              padding: EdgeInsetsDirectional.only(
                start: leadingWidget != null ? 8 : horizontalPadding,
                end: 8,
              ),
              child: Row(
                children: [
                  if (leadingWidget != null) ...[
                    leadingWidget,
                    const SizedBox(width: 4),
                  ],
                  Expanded(
                    child: title.isEmpty
                        ? const SizedBox.shrink()
                        : Semantics(
                            header: true,
                            child: Align(
                              alignment: AlignmentDirectional.centerStart,
                              child: FittedBox(
                                fit: BoxFit.scaleDown,
                                alignment: AlignmentDirectional.centerStart,
                                child: Text(
                                  title,
                                  maxLines: 1,
                                  softWrap: false,
                                  style: titleStyle,
                                ),
                              ),
                            ),
                          ),
                  ),
                  ...?actions,
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(toolbarHeight);
}
