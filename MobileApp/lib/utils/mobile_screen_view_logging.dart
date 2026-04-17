import 'package:flutter/widgets.dart';

import '../services/screen_view_tracker.dart';

/// Schedules `POST /api/mobile/v1/analytics/screen-view` for this screen so
/// [UserSessionLog] page-view histograms stay accurate.
///
/// [AnalyticsNavigatorObserver] already logs most [Navigator.pushNamed] routes,
/// but some admin flows (nested [Navigator] context, or timing) can miss a
/// notification — calling this from [State.initState] is safe: duplicates within
/// [ScreenViewTracker]'s dedup window are dropped.
void scheduleMobileScreenViewForRoutePath(
  BuildContext context, {
  required String routePath,
}) {
  WidgetsBinding.instance.addPostFrameCallback((_) {
    if (!context.mounted) return;
    final fromRoute = ModalRoute.of(context)?.settings.name;
    final path =
        (fromRoute != null && fromRoute.isNotEmpty) ? fromRoute : routePath;
    final tracker = ScreenViewTracker();
    final screenName = ScreenViewTracker.screenNameFromRoute(path);
    tracker.trackScreenView(
      screenName,
      screenClass: 'scheduleMobileScreenViewForRoutePath',
      routePath: path,
    );
  });
}
