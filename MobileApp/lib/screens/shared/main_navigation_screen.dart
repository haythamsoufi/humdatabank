import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../utils/debug_logger.dart';
import '../../utils/constants.dart';
import '../../utils/navigation_helper.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/notification_provider.dart';
import '../../providers/shared/tab_customization_provider.dart';
import '../../services/screen_view_tracker.dart';
// Screens used inside the tab navigation
import 'notifications_screen.dart';
import 'dashboard_screen.dart';
import 'settings_screen.dart';
import 'ai_chat_screen.dart';
import '../public/home_screen.dart';
import '../public/indicator_bank_screen.dart';
import '../public/resources_screen.dart';
import '../public/disaggregation_analysis_screen.dart';
import '../public/unified_planning_documents_screen.dart';
import '../admin/admin_screen.dart';
// Widgets
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/horizontal_swipe_page_view.dart';
import '../../widgets/offline_indicator.dart';

class MainNavigationScreen extends StatefulWidget {
  final int? initialTabIndex;

  const MainNavigationScreen({super.key, this.initialTabIndex});

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen>
    with WidgetsBindingObserver {
  late int _currentIndex;
  final GlobalKey _homeScreenKey = GlobalKey();
  late PageController _pageController;
  final ScreenViewTracker _screenViewTracker = ScreenViewTracker();
  bool _initialTabTracked = false;

  // Screen cache
  List<Widget>? _cachedScreens;
  List<String>? _cachedTabIds;
  int? _previousScreenCount;

  // Incremented on every authoritative navigation so stale post-frame callbacks
  // can detect they are outdated and skip backward corrections.
  int _navVersion = 0;

  Widget _screenForTabId(String tabId) {
    switch (tabId) {
      case TabIds.notifications:
        return const NotificationsScreen();
      case TabIds.dashboard:
        return const DashboardScreen();
      case TabIds.home:
        return HomeScreen(key: _homeScreenKey);
      case TabIds.unifiedPlanning:
        return const UnifiedPlanningDocumentsScreen();
      case TabIds.aiChat:
        return const AiChatScreen();
      case TabIds.admin:
        return const AdminScreen();
      case TabIds.analysis:
        return const DisaggregationAnalysisScreen();
      case TabIds.settings:
        return const SettingsScreen();
      case TabIds.resources:
        return const ResourcesScreen();
      case TabIds.indicators:
        return const IndicatorBankScreen();
      default:
        return const SizedBox.shrink();
    }
  }

  List<Widget> _buildScreensFromTabs(List<TabDefinition> tabs) {
    final ids = tabs.map((t) => t.id).toList();

    // Invalidate cache when tab set / order changed.
    final idsMatch = _cachedTabIds != null &&
        _cachedTabIds!.length == ids.length &&
        List.generate(ids.length, (i) => _cachedTabIds![i] == ids[i])
            .every((ok) => ok);

    if (_cachedScreens != null && idsMatch) {
      return _cachedScreens!;
    }

    if (_cachedScreens != null && !idsMatch) {
      DebugLogger.logNav('screen cache invalidated — tab list changed');
    }

    final screens = tabs.map((t) => _screenForTabId(t.id)).toList();
    _cachedScreens = screens;
    _cachedTabIds = ids;
    return screens;
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);

    _currentIndex = widget.initialTabIndex ?? 2;
    _pageController = PageController(initialPage: _currentIndex);
    _registerNavigation();
    DebugLogger.logNav('init — startPage=$_currentIndex');

    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      await _checkAuthStatus();
      if (!mounted) return;
      final auth = Provider.of<AuthProvider>(context, listen: false);
      if (auth.isAuthenticated) {
        await Provider.of<NotificationProvider>(context, listen: false)
            .refreshUnreadCount(authProvider: auth);
      }
      if (!mounted) return;
      await _loadTabPreferences();
    });
  }

  Future<void> _loadTabPreferences() async {
    final provider =
        Provider.of<TabCustomizationProvider>(context, listen: false);
    await provider.loadPreferences();
    if (mounted) setState(() {});
  }

  void _registerNavigation() {
    NavigationHelper.registerMainNavigation(
      owner: this,
      jump: (i) {
        if (!mounted) return;
        DebugLogger.logNav('jumpToPage $_currentIndex → $i');
        _navVersion++;
        _pageController.jumpToPage(i);
        setState(() => _currentIndex = i);
      },
      animate: (i) {
        if (!mounted || !_pageController.hasClients) return;
        DebugLogger.logNav('animateToPage $_currentIndex → $i');
        _navVersion++;
        _pageController.animateToPage(
          i,
          duration: AppConstants.animationMedium,
          curve: Curves.easeOutCubic,
        );
        setState(() => _currentIndex = i);
      },
    );
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      DebugLogger.logNav('lifecycle → background, clearing screen cache');
      _clearDistantScreens();
    } else if (state == AppLifecycleState.resumed) {
      DebugLogger.logNav('lifecycle → resumed');
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!mounted) return;
        final auth = Provider.of<AuthProvider>(context, listen: false);
        if (!auth.isAuthenticated) return;
        await Provider.of<NotificationProvider>(context, listen: false)
            .refreshUnreadCount(authProvider: auth);
      });
    }
  }

  void _clearDistantScreens() {
    if (_cachedScreens == null || _cachedScreens!.isEmpty) return;
    DebugLogger.logNav('screen cache cleared (currentPage=$_currentIndex)');
    setState(() {
      _cachedScreens = null;
      _cachedTabIds = null;
    });
  }

  /// Re-register navigation handlers whenever this widget is re-inserted into
  /// the tree (e.g. after a temporary deactivation during route transitions).
  /// This defends against edge cases where [dispose] of an old instance runs
  /// after [initState] of this instance and clears the static handlers.
  @override
  void activate() {
    super.activate();
    _registerNavigation();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    NavigationHelper.unregisterMainNavigation(this);
    _cachedScreens = null;
    _cachedTabIds = null;
    _pageController.dispose();
    super.dispose();
  }

  void _trackTabScreenView(int index, List<TabDefinition> tabs) {
    if (index >= 0 && index < tabs.length) {
      final tabId = tabs[index].id;
      final screenName = ScreenViewTracker.screenNameFromTabId(tabId);
      _screenViewTracker.trackScreenView(
        screenName,
        screenClass: 'MainNavigationScreen',
        routePath: '/tab/$tabId',
      );
    }
  }

  Future<void> _checkAuthStatus() async {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    await authProvider.checkAuthStatus();
  }

  @override
  Widget build(BuildContext context) {
    // Defensive guard: if the global navigation handler was unexpectedly cleared
    // (e.g. due to a race between pushNamedAndRemoveUntil and dispose on the
    // previous screen), reclaim ownership so bottom-nav taps work immediately.
    if (!NavigationHelper.isRegistered) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          DebugLogger.logNav(
              'build: handler missing — re-registering navigation');
          _registerNavigation();
        }
      });
    }

    return Consumer2<AuthProvider, TabCustomizationProvider>(
      builder: (context, authProvider, tabProvider, child) {
        final user = authProvider.user;
        final isAdmin = user?.isAdmin ?? false;
        final isFocalPoint = user?.isFocalPoint ?? false;
        final chatbotEnabled = user?.chatbotEnabled ?? false;
        final isAuthenticated = authProvider.isAuthenticated;

        // ── Get customized tab list ─────────────────────────────────────────
        final visibleTabs = tabProvider.getVisibleTabs(
          isAdmin: isAdmin,
          isAuthenticated: isAuthenticated,
          isFocalPoint: isFocalPoint,
          chatbotEnabled: chatbotEnabled,
        );

        final screens = _buildScreensFromTabs(visibleTabs);
        final homeIndex =
            visibleTabs.indexWhere((t) => t.id == TabIds.home);
        final defaultHomeIndex = homeIndex >= 0 ? homeIndex : 0;

        final initialIndex = widget.initialTabIndex ?? defaultHomeIndex;
        final targetIndex = _previousScreenCount == null
            ? (initialIndex < screens.length ? initialIndex : defaultHomeIndex)
            : (_currentIndex < screens.length
                ? _currentIndex
                : defaultHomeIndex);

        if (_previousScreenCount == null && widget.initialTabIndex != null) {
          _currentIndex = targetIndex;
        }

        final validIndex = targetIndex;

        if (_previousScreenCount != null &&
            _previousScreenCount != screens.length) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              final newIndex =
                  validIndex < screens.length ? validIndex : defaultHomeIndex;
              DebugLogger.logNav(
                  'screen count changed $_previousScreenCount → ${screens.length}, '
                  'recreating PageController at page=$newIndex');
              _pageController.dispose();
              _pageController = PageController(initialPage: newIndex);
              _registerNavigation();
              setState(() => _currentIndex = newIndex);
            }
          });
        }
        _previousScreenCount = screens.length;

        if (!_initialTabTracked) {
          _initialTabTracked = true;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) _trackTabScreenView(validIndex, visibleTabs);
          });
        }

        if (_currentIndex != validIndex) {
          final capturedVersion = _navVersion;
          DebugLogger.logNav(
              'build mismatch: _currentIndex=$_currentIndex validIndex=$validIndex '
              '— scheduling correction (v$capturedVersion)');
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted || !_pageController.hasClients) return;
            if (_navVersion != capturedVersion) {
              DebugLogger.logNav(
                  'post-frame correction SKIPPED — version changed '
                  '($capturedVersion → $_navVersion)');
              return;
            }
            DebugLogger.logNav(
                'post-frame correction: animateToPage $validIndex');
            _navVersion++;
            _pageController.animateToPage(validIndex,
                duration: AppConstants.animationMedium,
                curve: Curves.easeOutCubic);
            setState(() => _currentIndex = validIndex);
          });
        }

        // AiChatScreen manages its own keyboard insets (viewInsets.bottom
        // padding + inner resizeToAvoidBottomInset:true MediaQuery override).
        // Disable the outer Scaffold resize on that page to avoid double-inset.
        final onAiChatPage = chatbotEnabled &&
            _currentIndex >= 0 &&
            _currentIndex < visibleTabs.length &&
            visibleTabs[_currentIndex].id == TabIds.aiChat;

        // Tab pages (e.g. Indicator Bank) supply their own [AppBar]. This shell
        // has no app bar — keep [primary] false so child scaffolds own the
        // primary app bar and actions (e.g. propose icon) render correctly.
        return Scaffold(
          primary: false,
          backgroundColor: Theme.of(context).scaffoldBackgroundColor,
          resizeToAvoidBottomInset: !onAiChatPage,
          // [OfflineBanner] sits above [bottomNavigationBar] (anchored to body bottom).
          body: Stack(
            fit: StackFit.expand,
            clipBehavior: Clip.none,
            children: [
              Positioned.fill(
                child: HorizontalSwipePageView(
                  controller: _pageController,
                  onPageChanged: (index) {
                    DebugLogger.logNav(
                        'onPageChanged $_currentIndex → $index');
                    _navVersion++;
                    setState(() => _currentIndex = index);
                    _trackTabScreenView(index, visibleTabs);
                  },
                  children: screens,
                ),
              ),
              const Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: OfflineBanner(),
              ),
            ],
          ),
          bottomNavigationBar: AppBottomNavigationBar(
            currentIndex: validIndex,
            chatbotEnabled: chatbotEnabled,
            visibleTabs: visibleTabs,
            enableCustomization: true,
            onTap: (index) {
              if (index < 0 || index >= visibleTabs.length) return;

              if (index == defaultHomeIndex &&
                  validIndex == defaultHomeIndex) {
                DebugLogger.logNav('tap nav[$index] → home reload');
                HomeScreen.reloadFromKey(_homeScreenKey);
              } else {
                DebugLogger.logNav('tap nav[$index] → page[$index]');
                // Ensure we are the registered navigation handler before
                // animating.  After certain route transitions (e.g. logout
                // pushNamedAndRemoveUntil) the static handler can be cleared
                // before the new screen's first frame completes.
                if (!NavigationHelper.isRegistered) {
                  DebugLogger.logNav(
                      'tap nav[$index]: handler missing — re-registering first');
                  _registerNavigation();
                }
                NavigationHelper.animateToMainTab(index);
              }
            },
            isFocalPoint: isFocalPoint,
          ),
        );
      },
    );
  }
}
