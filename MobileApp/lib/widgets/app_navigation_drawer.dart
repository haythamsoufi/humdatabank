import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config/routes.dart';
import '../l10n/app_localizations.dart';
import '../models/shared/ai_chat_launch_args.dart';
import '../providers/shared/auth_provider.dart';
import '../providers/shared/language_provider.dart';
import '../utils/ios_constants.dart';
import '../utils/url_helper.dart';
import '../utils/navigation_helper.dart';
import '../providers/shared/tab_customization_provider.dart';
import 'modern_navigation_drawer.dart';

/// Identifies which screen currently hosts the drawer so tile behaviour
/// (active highlight, navigation depth) can adapt automatically.
enum ActiveDrawerScreen { home, indicatorBank, resources }

/// Shared navigation drawer used across top-level screens.
///
/// Reads [AuthProvider] and [LanguageProvider] from the widget tree so callers
/// only need to supply the active screen and two callbacks.
class AppNavigationDrawer extends StatelessWidget {
  const AppNavigationDrawer({
    super.key,
    required this.activeScreen,
    this.onHomeSelected,
    required this.onShowCountriesSheet,
  });

  final ActiveDrawerScreen activeScreen;

  /// Called when the Home tile is tapped while already on the home screen
  /// (e.g. scroll-to-top / reload).
  final VoidCallback? onHomeSelected;

  /// Called when the Countries tile is tapped (after the drawer is closed).
  final VoidCallback onShowCountriesSheet;

  bool get _isNested => activeScreen != ActiveDrawerScreen.home;

  /// Close the drawer, optionally pop the hosting route (for nested screens),
  /// then push [route].
  ///
  /// Set [alwaysPushOnTop] for "overlay" destinations (quiz, AI) that should
  /// stack on top of the current screen rather than replacing it.
  void _closeAndNavigate(
    BuildContext context,
    String route, {
    Object? arguments,
    bool alwaysPushOnTop = false,
  }) {
    Navigator.pop(context);
    if (_isNested && !alwaysPushOnTop) {
      Navigator.of(context).pop();
    }
    Navigator.of(context).pushNamed(route, arguments: arguments);
  }

  void _openUserSettings(BuildContext context) {
    Navigator.pop(context);
    if (_isNested) {
      Navigator.of(context).pop();
    }
    Navigator.of(context).pushNamed(AppRoutes.settings);
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final languageProvider = Provider.of<LanguageProvider>(
      context,
      listen: false,
    );
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAuthenticated = authProvider.isAuthenticated;
    final isFocalPoint = user?.isFocalPoint ?? false;
    final language = languageProvider.currentLanguage;

    final drawerWidth = math.min(
      MediaQuery.sizeOf(context).width * 0.88,
      320.0,
    );

    return Drawer(
      width: drawerWidth,
      backgroundColor: theme.colorScheme.surface,
      elevation: 2,
      shadowColor: Colors.black.withValues(alpha: 0.14),
      surfaceTintColor: Colors.transparent,
      shape: modernDrawerShape(),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ModernDrawerHeader(
              title: localizations.navigation,
              user: isAuthenticated ? user : null,
              onProfileTap: isAuthenticated
                  ? () => _openUserSettings(context)
                  : null,
              profileTapSemanticLabel: localizations.settings,
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(
                  0,
                  IOSSpacing.sm,
                  0,
                  IOSSpacing.lg,
                ),
                children: [
                  ModernDrawerTile(
                    icon: Icons.home_rounded,
                    title: localizations.home,
                    selected: activeScreen == ActiveDrawerScreen.home,
                    onTap: () {
                      if (activeScreen == ActiveDrawerScreen.home) {
                        Navigator.pop(context);
                        onHomeSelected?.call();
                      } else {
                        Navigator.pop(context);
                        Navigator.of(context).popUntil((route) {
                          return route.isFirst ||
                              route.settings.name == AppRoutes.dashboard;
                        });
                      }
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.library_books_rounded,
                    title: localizations.indicatorBank,
                    selected: activeScreen == ActiveDrawerScreen.indicatorBank,
                    onTap: () {
                      if (activeScreen == ActiveDrawerScreen.indicatorBank) {
                        Navigator.pop(context);
                      } else {
                        _closeAndNavigate(context, AppRoutes.indicatorBank);
                      }
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.quiz_rounded,
                    title: localizations.quizGame,
                    onTap: () => _closeAndNavigate(
                      context,
                      AppRoutes.quizGame,
                      alwaysPushOnTop: true,
                    ),
                  ),
                  ModernDrawerTile(
                    icon: Icons.smart_toy_outlined,
                    title: localizations.aiAssistant,
                    onTap: () => _closeAndNavigate(
                      context,
                      AppRoutes.aiChat,
                      arguments: AiChatLaunchArgs(
                        bottomNavTabIndex:
                            NavigationHelper.aiChatMainTabPageIndex(context),
                        startNewConversation: true,
                      ),
                      alwaysPushOnTop: true,
                    ),
                  ),
                  if (isFocalPoint)
                    ModernDrawerTile(
                      icon: Icons.notifications_rounded,
                      title: localizations.notifications,
                      onTap: () =>
                          _closeAndNavigate(context, AppRoutes.notifications),
                    )
                  else
                    ModernDrawerTile(
                      icon: Icons.folder_rounded,
                      title: localizations.resources,
                      selected: activeScreen == ActiveDrawerScreen.resources,
                      onTap: () {
                        if (activeScreen == ActiveDrawerScreen.resources) {
                          Navigator.pop(context);
                        } else {
                          _closeAndNavigate(context, AppRoutes.resources);
                        }
                      },
                    ),
                  ModernDrawerTile(
                    icon: Icons.description_rounded,
                    title: localizations.resourcesUnifiedPlanningSectionTitle,
                    onTap: () {
                      Navigator.pop(context);
                      if (_isNested) {
                        Navigator.of(context).pop();
                      }
                      final tabProvider = Provider.of<TabCustomizationProvider>(
                        context,
                        listen: false,
                      );
                      final idx = tabProvider.indexOfTab(
                        TabIds.unifiedPlanning,
                        isAdmin: user?.isAdmin ?? false,
                        isAuthenticated: isAuthenticated,
                        isFocalPoint: isFocalPoint,
                        chatbotEnabled: user?.chatbotEnabled ?? false,
                      );
                      if (idx >= 0) {
                        NavigationHelper.navigateToMainTab(context, idx);
                      } else {
                        Navigator.of(
                          context,
                        ).pushNamed(AppRoutes.unifiedPlanningDocuments);
                      }
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.public_rounded,
                    title: localizations.countries,
                    onTap: () {
                      Navigator.pop(context);
                      onShowCountriesSheet();
                    },
                  ),
                  ModernDrawerSectionTitle(
                    label: localizations.analysis.toUpperCase(),
                  ),
                  ModernDrawerTile(
                    icon: Icons.analytics_rounded,
                    title: localizations.disaggregationAnalysis,
                    onTap: () => _closeAndNavigate(
                      context,
                      AppRoutes.disaggregationAnalysis,
                    ),
                  ),
                  ModernDrawerTile(
                    icon: Icons.bar_chart_rounded,
                    title: localizations.dataVisualization,
                    onTap: () {
                      Navigator.pop(context);
                      if (_isNested) {
                        Navigator.of(context).pop();
                      }
                      final fullUrl = UrlHelper.buildFrontendUrlWithLanguage(
                        '/dataviz',
                        language,
                      );
                      Navigator.of(
                        context,
                      ).pushNamed(AppRoutes.webview, arguments: fullUrl);
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
