import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../config/app_navigation.dart';
import '../utils/constants.dart';
import 'routes.dart';
// Shared screens
import '../screens/shared/splash_screen.dart';
import '../screens/shared/login_screen.dart';
import '../screens/shared/azure_login_screen.dart';
import '../screens/shared/settings_screen.dart';
import '../screens/shared/ai_chat_screen.dart';
import '../screens/shared/main_navigation_screen.dart';
// Public screens
import '../screens/public/webview_screen.dart'
    show WebViewScreen, WebViewScreenArgs;
import '../screens/public/indicator_bank_screen.dart';
import '../screens/public/propose_indicator_screen.dart';
import '../screens/public/indicator_detail_screen.dart';
import '../screens/public/resources_screen.dart';
import '../screens/public/unified_planning_documents_screen.dart';
import '../screens/public/unified_planning_analytics_screen.dart';
import '../screens/public/disaggregation_analysis_screen.dart';
import '../screens/public/countries_screen.dart';
import '../screens/public/ns_structure_screen.dart';
import '../screens/public/quiz_game_screen.dart';
import '../screens/public/leaderboard_screen.dart';
// Admin screens
import '../screens/admin/templates_screen.dart';
import '../screens/admin/assignments_screen.dart';
import '../screens/admin/admin_screen.dart';
import '../screens/admin/admin_dashboard_screen.dart';
import '../screens/admin/document_management_screen.dart';
import '../screens/admin/translation_management_screen.dart';
import '../screens/admin/translation_entry_detail_screen.dart';
import '../screens/admin/resources_management_screen.dart';
import '../screens/admin/organizational_structure_screen.dart';
import '../screens/admin/indicator_bank_admin_screen.dart';
import '../screens/admin/edit_indicator_screen.dart';
import '../screens/admin/edit_entity_screen.dart';
import '../screens/admin/user_analytics_screen.dart';
import '../screens/admin/audit_trail_screen.dart';
import '../screens/admin/manage_users_screen.dart';
import '../screens/admin/access_requests_screen.dart';

/// Application router using go_router for declarative routing.
///
/// Migration from Navigator 1.0:
/// - Named routes are preserved for backward compatibility
/// - ShellRoute wraps the main navigation tabs
/// - Auth redirect is handled declaratively
/// - Deep linking is supported natively
///
/// The legacy [AppRouter] and [MaterialApp.routes] remain functional.
/// New screens should register routes here. Existing screens can be
/// migrated incrementally by adding their GoRoute and removing from
/// AppRouter.routes.
class AppGoRouter {
  AppGoRouter._();

  static GoRouter createRouter(BuildContext context) {
    return GoRouter(
      navigatorKey: appNavigatorKey,
      initialLocation: AppRoutes.splash,
      debugLogDiagnostics: true,
      routes: [
        GoRoute(
          path: AppRoutes.splash,
          name: 'splash',
          builder: (context, state) => const SplashScreen(),
        ),
        GoRoute(
          path: AppRoutes.login,
          name: 'login',
          builder: (context, state) => const LoginScreen(),
        ),
        GoRoute(
          path: AppRoutes.azureLogin,
          name: 'azureLogin',
          builder: (context, state) => const AzureLoginScreen(),
        ),

        // Main app with bottom navigation
        GoRoute(
          path: AppRoutes.dashboard,
          name: 'dashboard',
          builder: (context, state) {
            final tabIndex = state.extra is int ? state.extra as int : 1;
            return MainNavigationScreen(initialTabIndex: tabIndex);
          },
        ),
        GoRoute(
          path: AppRoutes.notifications,
          name: 'notifications',
          builder: (context, state) {
            final tabIndex = state.extra is int ? state.extra as int : 0;
            return MainNavigationScreen(initialTabIndex: tabIndex);
          },
        ),

        // Settings
        GoRoute(
          path: AppRoutes.settings,
          name: 'settings',
          builder: (context, state) => const SettingsScreen(),
        ),

        // AI Chat with slide transition
        GoRoute(
          path: AppRoutes.aiChat,
          name: 'aiChat',
          pageBuilder: (context, state) => CustomTransitionPage(
            key: state.pageKey,
            child: const AiChatScreenWithBottomNav(),
            transitionsBuilder: (context, animation, secondaryAnimation, child) {
              final slideTween = Tween<Offset>(
                begin: const Offset(1.0, 0.0),
                end: Offset.zero,
              ).chain(CurveTween(curve: Curves.easeOutCubic));
              return SlideTransition(
                position: animation.drive(slideTween),
                child: child,
              );
            },
            transitionDuration: AppConstants.animationMedium,
            reverseTransitionDuration: AppConstants.animationMedium,
          ),
        ),

        // WebView
        GoRoute(
          path: '/webview',
          name: 'webview',
          builder: (context, state) {
            final args = WebViewScreenArgs.parse(state.extra);
            return WebViewScreen(
              initialUrl: args.initialUrl,
              forceOfflineAssignmentBundle: args.forceOfflineAssignmentBundle,
              offlineAssignmentId: args.offlineAssignmentId,
            );
          },
        ),

        // Public screens
        GoRoute(
          path: '/indicator-bank',
          name: 'indicatorBank',
          builder: (context, state) => const IndicatorBankScreen(),
          routes: [
            GoRoute(
              path: 'propose',
              name: 'proposeIndicator',
              builder: (context, state) => const ProposeIndicatorScreen(),
            ),
            GoRoute(
              path: ':id',
              name: 'indicatorDetail',
              builder: (context, state) {
                final id = int.parse(state.pathParameters['id']!);
                return IndicatorDetailScreen(indicatorId: id);
              },
            ),
          ],
        ),
        GoRoute(
          path: '/resources',
          name: 'resources',
          builder: (context, state) => const ResourcesScreen(),
        ),
        GoRoute(
          path: AppRoutes.unifiedPlanningDocuments,
          name: 'unifiedPlanningDocuments',
          builder: (context, state) =>
              const UnifiedPlanningDocumentsScreen(),
        ),
        GoRoute(
          path: AppRoutes.unifiedPlanningAnalytics,
          name: 'unifiedPlanningAnalytics',
          builder: (context, state) =>
              const UnifiedPlanningAnalyticsScreen(),
        ),
        GoRoute(
          path: '/disaggregation-analysis',
          name: 'disaggregationAnalysis',
          builder: (context, state) => const DisaggregationAnalysisScreen(),
        ),
        GoRoute(
          path: '/countries',
          name: 'countries',
          builder: (context, state) => const CountriesScreen(),
        ),
        GoRoute(
          path: '/ns-structure',
          name: 'nsStructure',
          builder: (context, state) => const NSStructureScreen(),
          routes: [
            GoRoute(
              path: ':id',
              name: 'nsStructureDetail',
              builder: (context, state) {
                final id = int.parse(state.pathParameters['id']!);
                return NSStructureScreen(countryId: id);
              },
            ),
          ],
        ),
        GoRoute(
          path: '/quiz-game',
          name: 'quizGame',
          builder: (context, state) => const QuizGameScreen(),
        ),
        GoRoute(
          path: '/leaderboard',
          name: 'leaderboard',
          builder: (context, state) => const LeaderboardScreen(),
        ),

        // Admin screens
        GoRoute(
          path: '/admin',
          name: 'admin',
          builder: (context, state) => const AdminScreen(showBottomNav: true),
          routes: [
            GoRoute(
              path: 'dashboard',
              name: 'adminDashboard',
              builder: (context, state) => const AdminDashboardScreen(showBottomNav: true),
            ),
            GoRoute(
              path: 'templates',
              name: 'templates',
              builder: (context, state) => const TemplatesScreen(),
            ),
            GoRoute(
              path: 'assignments',
              name: 'assignments',
              builder: (context, state) => const AssignmentsScreen(),
            ),
            GoRoute(
              path: 'users',
              name: 'users',
              builder: (context, state) => const ManageUsersScreen(),
            ),
            GoRoute(
              path: 'access-requests',
              name: 'accessRequests',
              builder: (context, state) => const AccessRequestsScreen(),
            ),
            GoRoute(
              path: 'documents',
              name: 'documentManagement',
              builder: (context, state) => const DocumentManagementScreen(),
            ),
            GoRoute(
              path: 'translations/manage',
              name: 'translationManagement',
              builder: (context, state) => const TranslationManagementScreen(),
            ),
            GoRoute(
              path: 'translations/entry',
              name: 'translationEntryDetail',
              builder: (context, state) {
                final extra = state.extra;
                Map<String, dynamic>? map;
                if (extra is Map<String, dynamic>) {
                  map = extra;
                } else if (extra is Map) {
                  map = Map<String, dynamic>.from(extra);
                }
                if (map == null) {
                  return const Scaffold(
                    body: Center(child: Text('Missing translation data.')),
                  );
                }
                return TranslationEntryDetailScreen(entry: map);
              },
            ),
            GoRoute(
              path: 'resources',
              name: 'resourcesManagement',
              builder: (context, state) => const ResourcesManagementScreen(),
            ),
            GoRoute(
              path: 'organization',
              name: 'organizationalStructure',
              builder: (context, state) => const OrganizationalStructureScreen(),
              routes: [
                GoRoute(
                  path: 'edit/:id',
                  name: 'editEntity',
                  builder: (context, state) {
                    final id = int.parse(state.pathParameters['id']!);
                    final args = state.extra is Map ? state.extra as Map : null;
                    return EditEntityScreen(
                      entityId: id,
                      entityType: args?['entityType'],
                      entityName: args?['entityName'],
                    );
                  },
                ),
                GoRoute(
                  path: 'edit/:entityType/:id',
                  name: 'editEntityTyped',
                  builder: (context, state) {
                    final id = int.parse(state.pathParameters['id']!);
                    final entityType = state.pathParameters['entityType'];
                    final args = state.extra is Map ? state.extra as Map : null;
                    return EditEntityScreen(
                      entityId: id,
                      entityType: entityType,
                      entityName: args?['entityName'],
                    );
                  },
                ),
              ],
            ),
            GoRoute(
              path: 'indicator_bank',
              name: 'indicatorBankAdmin',
              builder: (context, state) => const IndicatorBankAdminScreen(),
              routes: [
                GoRoute(
                  path: 'edit/:id',
                  name: 'editIndicator',
                  builder: (context, state) {
                    final id = int.parse(state.pathParameters['id']!);
                    return EditIndicatorScreen(indicatorId: id);
                  },
                ),
              ],
            ),
            GoRoute(
              path: 'analytics/dashboard',
              name: 'userAnalytics',
              builder: (context, state) => const UserAnalyticsScreen(),
            ),
            GoRoute(
              path: 'analytics/audit-trail',
              name: 'auditTrail',
              builder: (context, state) => const AuditTrailScreen(),
            ),
          ],
        ),
      ],
      errorBuilder: (context, state) => Scaffold(
        body: Center(
          child: Text('Route not found: ${state.uri}'),
        ),
      ),
    );
  }
}
