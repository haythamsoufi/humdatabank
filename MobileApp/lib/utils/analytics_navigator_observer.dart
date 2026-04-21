import 'package:flutter/material.dart';
import '../services/screen_view_tracker.dart';

class AnalyticsNavigatorObserver extends NavigatorObserver {
  final ScreenViewTracker _tracker = ScreenViewTracker();

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPush(route, previousRoute);
    _logScreenView(route);
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
    if (newRoute != null) {
      _logScreenView(newRoute);
    }
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    super.didPop(route, previousRoute);
    if (previousRoute != null) {
      _logScreenView(previousRoute);
    }
  }

  void _logScreenView(Route<dynamic> route) {
    final routeName = route.settings.name;
    if (routeName != null && routeName.isNotEmpty) {
      final screenName = ScreenViewTracker.screenNameFromRoute(routeName);
      _tracker.trackScreenView(
        screenName,
        screenClass: route.runtimeType.toString(),
        routePath: routeName,
      );
    }
  }
}
