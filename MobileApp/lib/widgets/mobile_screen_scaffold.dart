import 'package:flutter/material.dart';

/// Pushed-route scaffold: consistent background and optional app bar.
///
/// Tab roots stay under [MainNavigationScreen]; use this for full-screen routes
/// pushed on the stack. Compose async content with [AsyncBody] when needed.
class MobileScreenScaffold extends StatelessWidget {
  const MobileScreenScaffold({
    super.key,
    this.appBar,
    required this.body,
    this.backgroundColor,
    this.resizeToAvoidBottomInset,
    this.bottomNavigationBar,
    this.floatingActionButton,
    this.safeArea = true,
  });

  final PreferredSizeWidget? appBar;
  final Widget body;
  final Color? backgroundColor;
  final bool? resizeToAvoidBottomInset;
  final Widget? bottomNavigationBar;
  final Widget? floatingActionButton;

  /// When true (default), wraps [body] in [SafeArea].
  final bool safeArea;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    Widget content = body;
    if (safeArea) {
      content = SafeArea(child: content);
    }
    return Scaffold(
      appBar: appBar,
      backgroundColor: backgroundColor ?? theme.scaffoldBackgroundColor,
      resizeToAvoidBottomInset: resizeToAvoidBottomInset,
      bottomNavigationBar: bottomNavigationBar,
      floatingActionButton: floatingActionButton,
      body: content,
    );
  }
}
