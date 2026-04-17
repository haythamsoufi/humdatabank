import 'package:flutter/material.dart';

import 'mobile_screen_view_logging.dart';

/// Calls [scheduleMobileScreenViewForRoutePath] from [initState] for admin analytics routes.
///
/// Apply after other `State` mixins (e.g. [SingleTickerProviderStateMixin]) so
/// `super.initState()` still initializes tickers/controllers in subclasses.
mixin AdminScreenViewLoggingMixin<T extends StatefulWidget> on State<T> {
  String get adminScreenViewRoutePath;

  @override
  void initState() {
    super.initState();
    scheduleMobileScreenViewForRoutePath(
      context,
      routePath: adminScreenViewRoutePath,
    );
  }
}
