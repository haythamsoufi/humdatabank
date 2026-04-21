import 'package:flutter/widgets.dart';

import '../services/screen_view_tracker.dart';

/// Schedules `POST /api/mobile/v1/analytics/screen-view` for this screen so
/// [UserSessionLog] page-view histograms stay accurate.
///
/// [AnalyticsNavigatorObserver] already logs most [Navigator.pushNamed] routes,
/// but some admin flows (nested [Navigator] context, or timing) can miss a
/// notification — calling this from [State.initState] is safe: duplicates within
/// [ScreenViewTracker]'s dedup window are dropped.
///
/// Always uses [routePath] for the server payload. Do **not** prefer
/// [ModalRoute.of] here: when the app shell is [MainNavigationScreen]
/// (`/dashboard`), the nearest modal route can remain the dashboard route even
/// after a push, which would mis-label every admin sub-screen as `Home` and
/// collide with Backoffice `screen_name`-only dedup on
/// `POST /analytics/screen-view`.
void scheduleMobileScreenViewForRoutePath(
  BuildContext context, {
  required String routePath,
}) {
  WidgetsBinding.instance.addPostFrameCallback((_) {
    if (!context.mounted) return;
    final path = routePath;
    final tracker = ScreenViewTracker();
    final screenName = ScreenViewTracker.screenNameFromRoute(path);
    tracker.trackScreenView(
      screenName,
      screenClass: 'scheduleMobileScreenViewForRoutePath',
      routePath: path,
    );
  });
}
