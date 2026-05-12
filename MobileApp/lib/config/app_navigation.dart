import 'package:flutter/material.dart';

/// Root [Navigator] key for push notifications, launcher shortcuts, and similar.
final GlobalKey<NavigatorState> appNavigatorKey = GlobalKey<NavigatorState>();

/// Push on the same [Navigator] as [MaterialApp.navigatorKey] so
/// [AnalyticsNavigatorObserver] receives [Route.didPush] with a proper
/// [RouteSettings.name] (histogram `/m/...` keys). Prefer this over
/// [Navigator.of] from deep tab/page contexts.
Future<T?> pushNamedOnRootNavigator<T extends Object?>(
  BuildContext context,
  String routeName, {
  Object? arguments,
}) {
  final state = appNavigatorKey.currentState;
  if (state != null) {
    return state.pushNamed<T>(routeName, arguments: arguments);
  }
  return Navigator.of(context, rootNavigator: true)
      .pushNamed<T>(routeName, arguments: arguments);
}
