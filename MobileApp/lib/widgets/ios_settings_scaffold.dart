import 'package:flutter/material.dart';

import '../utils/ios_settings_style.dart';
import 'app_bar.dart';

/// Settings-style page: shared [AppAppBar] header over a grouped background list.
class IOSSettingsPageScaffold extends StatelessWidget {
  const IOSSettingsPageScaffold({
    super.key,
    required this.title,
    required this.children,
    this.materialAppBarActions,
    this.bottomNavigationBar,
  });

  /// Shown as the [AppAppBar] title.
  final String title;

  final List<Widget> children;

  final List<Widget>? materialAppBarActions;

  /// Optional bottom bar (e.g. [AppBottomNavigationBar] when this page is not inside tab shell).
  final Widget? bottomNavigationBar;

  @override
  Widget build(BuildContext context) {
    final bg = IOSSettingsStyle.groupedTableBackground(context);

    return Scaffold(
      appBar: AppAppBar(title: title, actions: materialAppBarActions),
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
}
