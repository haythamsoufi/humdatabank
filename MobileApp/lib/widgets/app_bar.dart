import 'package:flutter/material.dart';

class AppAppBar extends StatelessWidget implements PreferredSizeWidget {
  final String title;
  final List<Widget>? actions;
  final Widget? leading;
  final bool automaticallyImplyLeading;
  final bool useLargeTitle;

  const AppAppBar({
    super.key,
    required this.title,
    this.actions,
    this.leading,
    this.automaticallyImplyLeading = true,
    this.useLargeTitle = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final textTheme = theme.textTheme;

    // iOS-style large title
    if (useLargeTitle) {
      return SliverAppBar(
        pinned: true,
        elevation: 0,
        backgroundColor: theme.appBarTheme.backgroundColor,
        foregroundColor: theme.appBarTheme.foregroundColor,
        surfaceTintColor: Colors.transparent,
        leading: leading,
        automaticallyImplyLeading: automaticallyImplyLeading,
        actions: actions,
        expandedHeight: 96,
        // Must be >= [toolbarHeight] (default [kToolbarHeight]); a smaller
        // collapsed height fails SliverAppBar's assertion on current Flutter SDKs.
        toolbarHeight: kToolbarHeight,
        collapsedHeight: kToolbarHeight,
        flexibleSpace: FlexibleSpaceBar(
          titlePadding: const EdgeInsets.only(left: 16, bottom: 16, right: 16),
          title: Text(
            title,
            style: (textTheme.headlineLarge ?? const TextStyle()).copyWith(
              fontWeight: FontWeight.w700,
              color: theme.appBarTheme.foregroundColor,
            ),
          ),
        ),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(0.5),
          child: Container(
            color: theme.dividerColor.withValues(alpha: 0.5),
            height: 0.5,
          ),
        ),
      );
    }

    // Standard iOS-style title
    return AppBar(
      elevation: 0,
      backgroundColor: theme.appBarTheme.backgroundColor,
      foregroundColor: theme.appBarTheme.foregroundColor,
      surfaceTintColor: Colors.transparent,
      title: Text(
        title,
        style: textTheme.titleLarge!.copyWith(
          fontWeight: FontWeight.w600,
          color: theme.appBarTheme.foregroundColor,
        ),
      ),
      leading: leading,
      automaticallyImplyLeading: automaticallyImplyLeading,
      actions: actions,
      centerTitle: false,
      bottom: PreferredSize(
        preferredSize: const Size.fromHeight(0.5),
        child: Container(
          color: theme.dividerColor.withValues(alpha: 0.5),
          height: 0.5,
        ),
      ),
    );
  }

  @override
  Size get preferredSize => useLargeTitle
      ? const Size.fromHeight(96)
      : const Size.fromHeight(kToolbarHeight);
}
