import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/scheduler.dart';
import 'package:quick_actions/quick_actions.dart';

import '../config/app_navigation.dart';
import '../config/routes.dart';
import '../models/shared/ai_chat_launch_args.dart';
import '../utils/navigation_helper.dart';

/// iOS: Home screen quick actions (long-press app icon).
/// Android: App shortcuts (API 25+; long-press icon, can pin to home on many launchers).
class LauncherShortcutsService {
  LauncherShortcutsService._();

  static const String typeAiChat = 'ai_chat';

  static String? _pendingRoute;

  /// Set after [SplashScreen] leaves the stack so we never push chat on top of splash.
  static bool _splashNavigationFinished = false;

  /// Register shortcuts and handle taps. Call after [WidgetsFlutterBinding.ensureInitialized].
  static Future<void> install() async {
    if (kIsWeb) return;
    if (!Platform.isIOS && !Platform.isAndroid) return;

    const qa = QuickActions();
    await qa.initialize((type) {
      if (type == typeAiChat) {
        _pendingRoute = AppRoutes.aiChat;
        SchedulerBinding.instance.addPostFrameCallback((_) {
          tryFlushPendingNavigation();
        });
      }
    });

    await qa.setShortcutItems(const <ShortcutItem>[
      ShortcutItem(
        type: typeAiChat,
        localizedTitle: 'AI Chat',
        localizedSubtitle: 'Open the chatbot',
      ),
    ]);
  }

  /// Call from [SplashScreen] after [Navigator.pushReplacementNamed] to the main shell.
  static void markSplashFinished() {
    _splashNavigationFinished = true;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      tryFlushPendingNavigation();
    });
  }

  /// Opens [AiChatScreen] when a shortcut was chosen and splash has finished.
  static void tryFlushPendingNavigation() {
    if (!_splashNavigationFinished) return;

    final nav = appNavigatorKey.currentState;
    if (nav == null || !nav.mounted) return;

    final pending = _pendingRoute;
    if (pending == null) return;

    _pendingRoute = null;
    if (pending == AppRoutes.aiChat) {
      nav.pushNamed(
        pending,
        arguments: AiChatLaunchArgs(
          bottomNavTabIndex:
              NavigationHelper.aiChatMainTabPageIndex(nav.context),
          startNewConversation: true,
        ),
      );
    } else {
      nav.pushNamed(pending);
    }
  }
}
