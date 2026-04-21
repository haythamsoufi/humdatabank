import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:provider/provider.dart';
import '../config/routes.dart';
import '../providers/shared/auth_provider.dart';
import '../providers/shared/tab_customization_provider.dart';
import '../widgets/bottom_navigation_bar.dart';
import 'debug_logger.dart';

/// Utility class for handling navigation to MainNavigationScreen with tab switching.
///
/// ## PageView registration
/// [MainNavigationScreen] calls [registerMainNavigation] in `initState` and
/// [unregisterMainNavigation] in `dispose`. This gives any screen a direct
/// handle to animate/jump the PageView without going through the Navigator.
///
/// ## AI chat tab
/// The AI chat screen is a regular [PageView] page; its index depends on the
/// visible tab set (see [TabCustomizationProvider], [AppBottomNavigationBar.aiChatNavIndex]).
/// All tab transitions are uniform horizontal PageView swipes with no push/pop involved.
class NavigationHelper {
  // ---------------------------------------------------------------------------
  // PageView registration — set by MainNavigationScreen
  // ---------------------------------------------------------------------------

  static void Function(int)? _jumpToTab;
  static void Function(int)? _animateToTab;

  /// Identity of the [State] instance that last registered.
  ///
  /// During [Navigator.pushReplacementNamed] Flutter runs the *new* route's
  /// `initState` before the *old* route's `dispose`. Without this token the
  /// old `dispose` would unconditionally clear handlers that the new instance
  /// already registered, leaving `_animateToTab == null` and silently breaking
  /// every subsequent bottom-nav tap.
  static Object? _registrationOwner;

  /// Pass `owner: this` (the [State] instance) so that [unregisterMainNavigation]
  /// can skip the clear when a newer instance has already taken over.
  static void registerMainNavigation({
    required Object owner,
    required void Function(int pageIndex) jump,
    required void Function(int pageIndex) animate,
  }) {
    _registrationOwner = owner;
    _jumpToTab = jump;
    _animateToTab = animate;
    DebugLogger.logNav('NavigationHelper: MainNavigation registered');
  }

  /// `true` when a [MainNavigationScreen] has registered its handlers.
  /// Used as a defensive guard to trigger re-registration when navigation
  /// handlers are unexpectedly null.
  static bool get isRegistered => _animateToTab != null;

  /// Only clears the handlers when [owner] is still the current registrant.
  /// If a newer [MainNavigationScreen] instance registered first (which happens
  /// during [Navigator.pushReplacementNamed]), this is a no-op.
  static void unregisterMainNavigation(Object owner) {
    if (_registrationOwner != owner) {
      DebugLogger.logNav(
          'NavigationHelper: unregister skipped — newer owner already registered');
      return;
    }
    _registrationOwner = null;
    _jumpToTab = null;
    _animateToTab = null;
    DebugLogger.logNav('NavigationHelper: MainNavigation unregistered');
  }

  /// Instantly repositions the main [PageView] to [pageIndex] with no animation.
  static void jumpToMainTab(int pageIndex) {
    DebugLogger.logNav('NavigationHelper: jumpToMainTab → page[$pageIndex]'
        '${_jumpToTab == null ? " (no handler!)" : ""}');
    _jumpToTab?.call(pageIndex);
  }

  /// Animates the main [PageView] to [pageIndex].
  static void animateToMainTab(int pageIndex) {
    if (_animateToTab == null) {
      DebugLogger.logNav(
          'NavigationHelper: animateToMainTab → page[$pageIndex] (no handler! '
          'owner=$_registrationOwner)');
    } else {
      DebugLogger.logNav(
          'NavigationHelper: animateToMainTab → page[$pageIndex]');
    }
    _animateToTab?.call(pageIndex);
  }

  // ---------------------------------------------------------------------------
  // Route navigation
  // ---------------------------------------------------------------------------

  /// Navigate to [MainNavigationScreen] at [tabIndex] (PageView page index).
  ///
  /// Pops all routes until the main screen, then pushes a replacement.
  /// Used from deeply nested screens; prefer [animateToMainTab] when the main
  /// screen is already the active route.
  static void navigateToMainTab(BuildContext context, int tabIndex) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAdmin = user?.isAdmin ?? false;
    final isFocalPoint = user?.isFocalPoint ?? false;

    Navigator.of(context).popUntil((route) {
      final routeName = route.settings.name;
      return route.isFirst ||
          routeName == AppRoutes.dashboard ||
          routeName == AppRoutes.notifications;
    });

    if (tabIndex == 0 && (isAdmin || isFocalPoint)) {
      Navigator.of(context).pushReplacementNamed(
        AppRoutes.notifications,
        arguments: tabIndex,
      );
    } else {
      Navigator.of(context).pushReplacementNamed(
        AppRoutes.dashboard,
        arguments: tabIndex,
      );
    }
  }

  /// Navigates to the AI chat tab.
  ///
  /// If [MainNavigationScreen] is active (registered), animates the PageView
  /// to the AI chat page in place. Otherwise pops to the main screen first.
  ///
  /// AI chat is now a regular PageView page — no route is pushed.
  /// Page index of the AI chat tab for the current role / customization / chatbot flag.
  static int aiChatMainTabPageIndex(BuildContext context) {
    return _resolveTabIndex(
      context,
      TabIds.aiChat,
      fallback: AppBottomNavigationBar.aiChatNavIndex,
    );
  }

  static void openAiChat(BuildContext context) {
    final aiPage = _resolveTabIndex(context, TabIds.aiChat,
        fallback: AppBottomNavigationBar.aiChatNavIndex);
    if (aiPage < 0) return;
    if (_animateToTab != null) {
      DebugLogger.logNav('NavigationHelper: openAiChat → animateTo page[$aiPage]');
      _animateToTab!(aiPage);
    } else {
      DebugLogger.logNav('NavigationHelper: openAiChat → navigateToMainTab[$aiPage]');
      navigateToMainTab(context, aiPage);
    }
  }

  /// Pops until [AppRoutes.dashboard] (or first route), then navigates to the
  /// AI chat tab if [navIndex] matches the AI chat slot and chatbot is enabled.
  static void popToMainThenOpenAiIfNeeded(BuildContext context, int navIndex) {
    final chatbot =
        Provider.of<AuthProvider>(context, listen: false).user?.chatbotEnabled ??
            false;
    final navigator = Navigator.of(context);
    navigator.popUntil((route) {
      return route.isFirst || route.settings.name == AppRoutes.dashboard;
    });
    final aiPage = _resolveTabIndex(context, TabIds.aiChat,
        fallback: AppBottomNavigationBar.aiChatNavIndex);
    if (!chatbot || navIndex != aiPage || aiPage < 0) return;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      animateToMainTab(aiPage);
    });
  }

  // ── Provider-aware tab lookup ───────────────────────────────────────────

  /// Returns the index of [tabId] in the current customized visible tabs,
  /// falling back to [fallback] when the provider is unavailable.
  static int _resolveTabIndex(BuildContext context, String tabId,
      {required int fallback}) {
    try {
      final provider =
          Provider.of<TabCustomizationProvider>(context, listen: false);
      final auth = Provider.of<AuthProvider>(context, listen: false);
      final user = auth.user;
      final idx = provider.indexOfTab(
        tabId,
        isAdmin: user?.isAdmin ?? false,
        isAuthenticated: auth.isAuthenticated,
        isFocalPoint: user?.isFocalPoint ?? false,
        chatbotEnabled: user?.chatbotEnabled ?? false,
      );
      return idx >= 0 ? idx : fallback;
    } catch (_) {
      return fallback;
    }
  }
}
