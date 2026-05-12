import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;

import '../utils/ios_settings_style.dart';
import 'app_bar.dart';

/// Settings-style page: iOS sliver nav (inline title) + grouped background, or Material app bar + list.
class IOSSettingsPageScaffold extends StatelessWidget {
  const IOSSettingsPageScaffold({
    super.key,
    required this.title,
    required this.children,
    this.materialAppBarActions,
    this.bottomNavigationBar,
  });

  /// Shown in the navigation bar on iOS and as [AppAppBar] title on other platforms.
  final String title;

  final List<Widget> children;

  final List<Widget>? materialAppBarActions;

  /// Optional bottom bar (e.g. [AppBottomNavigationBar] when this page is not inside tab shell).
  final Widget? bottomNavigationBar;

  @override
  Widget build(BuildContext context) {
    final bg = IOSSettingsStyle.groupedTableBackground(context);

    if (IOSSettingsStyle.useIosSettingsChrome) {
      // CupertinoPageScaffold + CupertinoNavigationBar gives a true compact
      // inline nav bar (title on the same row as the back control), which is
      // the correct iOS pattern for settings sub-pages. CupertinoSliverNavigationBar
      // with largeTitle puts the title on a second row; without largeTitle it
      // mis-behaves as a sliver (content hidden / grey screen).
      final scroll = ListView(
        padding: EdgeInsets.zero,
        physics: IOSSettingsStyle.pageScrollPhysics(),
        children: children,
      );

      final Widget body;
      if (bottomNavigationBar != null) {
        body = Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: SafeArea(
                bottom: false,
                child: ColoredBox(
                  color: bg,
                  child: scroll,
                ),
              ),
            ),
            SafeArea(
              top: false,
              child: bottomNavigationBar!,
            ),
          ],
        );
      } else {
        body = SafeArea(
          child: ColoredBox(
            color: bg,
            child: scroll,
          ),
        );
      }

      return cupertino.CupertinoPageScaffold(
        backgroundColor: bg,
        navigationBar: cupertino.CupertinoNavigationBar(
          middle: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: _iosNavTitleStyle(context),
          ),
          backgroundColor: bg,
          border: IOSSettingsStyle.navigationBarBottomBorder(context),
        ),
        child: body,
      );
    }

    return Scaffold(
      appBar: AppAppBar(
        title: title,
        actions: materialAppBarActions,
      ),
      backgroundColor: bg,
      bottomNavigationBar: bottomNavigationBar,
      body: SafeArea(
        bottom: bottomNavigationBar == null,
        child: ColoredBox(
          color: bg,
          child: ListView(
            padding: EdgeInsets.zero,
            physics: IOSSettingsStyle.pageScrollPhysics(),
            children: children,
          ),
        ),
      ),
    );
  }

  /// Applies the Material text theme font (Tajawal or system default) to
  /// Cupertino's nav title metrics so the bar matches the rest of the app.
  static TextStyle _iosNavTitleStyle(BuildContext context) {
    final cupertinoTheme = cupertino.CupertinoTheme.of(context);
    final base = cupertinoTheme.textTheme.navTitleTextStyle;
    final materialTitle = Theme.of(context).textTheme.titleMedium;
    final family = materialTitle?.fontFamily;
    if (family != null && family.isNotEmpty) {
      return base.copyWith(
        fontFamily: family,
        fontFamilyFallback: materialTitle?.fontFamilyFallback,
      );
    }
    return base;
  }
}
