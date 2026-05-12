import 'package:flutter/material.dart';
import 'routes.dart';
import '../utils/constants.dart';
import '../widgets/app_bar.dart';
// Shared screens
import '../screens/shared/splash_screen.dart';
import '../screens/shared/login_screen.dart';
import '../screens/shared/azure_login_screen.dart';
import '../screens/shared/settings_screen.dart';
import '../screens/shared/ai_chat_screen.dart';
import '../screens/shared/main_navigation_screen.dart';
// Public screens
import '../screens/public/pdf_viewer_screen.dart';
import '../screens/public/webview_screen.dart' show WebViewScreen, WebViewScreenArgs;
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
import '../screens/admin/assignment_detail_screen.dart';
import '../models/admin/admin_assignment.dart';
import '../l10n/app_localizations.dart';
import '../screens/admin/admin_screen.dart';
import '../screens/admin/admin_dashboard_screen.dart';
import '../screens/admin/document_management_screen.dart';
import '../screens/admin/document_detail_screen.dart';
import '../screens/admin/resource_detail_screen.dart';
import '../models/shared/document.dart';
import '../models/shared/resource.dart';
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

/// Legacy Navigator 1.0 router — routes and onGenerateRoute.
///
/// **Migration**: New screens should be added to [AppGoRouter] in
/// `go_router_config.dart` instead. This file is retained for backward
/// compatibility while the migration is in progress.
///
/// To switch the app to go_router, change [MaterialApp] in `main.dart` to
/// [MaterialApp.router] and pass [AppGoRouter.createRouter] as the
/// `routerConfig`. The legacy [routes] and [onGenerateRoute] can then be
/// removed.
class AppRouter {
  static Map<String, WidgetBuilder> get routes => {
        AppRoutes.splash: (context) => const SplashScreen(),
        AppRoutes.login: (context) => const LoginScreen(),
        AppRoutes.azureLogin: (context) => const AzureLoginScreen(),
        AppRoutes.dashboard: (context) {
          final args = ModalRoute.of(context)?.settings.arguments;
          // Pass null when no argument is provided so MainNavigationScreen
          // defaults to the home tab (index 2 via `widget.initialTabIndex ?? 2`).
          // Explicit int arguments (e.g. from navigateToMainTab) are still honoured.
          final tabIndex = args is int ? args : null;
          return MainNavigationScreen(initialTabIndex: tabIndex);
        },
        AppRoutes.settings: (context) => const SettingsScreen(),
        AppRoutes.notifications: (context) {
          final args = ModalRoute.of(context)?.settings.arguments;
          final tabIndex = args is int ? args : 0;
          return MainNavigationScreen(initialTabIndex: tabIndex);
        },
        AppRoutes.admin: (context) => const AdminScreen(showBottomNav: true),
        AppRoutes.adminDashboard: (context) =>
            const AdminDashboardScreen(showBottomNav: true),
        AppRoutes.templates: (context) => const TemplatesScreen(),
        AppRoutes.assignments: (context) => const AssignmentsScreen(),
        AppRoutes.users: (context) => const ManageUsersScreen(),
        AppRoutes.accessRequests: (context) => const AccessRequestsScreen(),
        AppRoutes.documentManagement: (context) =>
            const DocumentManagementScreen(),
        AppRoutes.translationManagement: (context) =>
            const TranslationManagementScreen(),
        AppRoutes.resourcesManagement: (context) =>
            const ResourcesManagementScreen(),
        AppRoutes.organizationalStructure: (context) =>
            const OrganizationalStructureScreen(),
        AppRoutes.indicatorBankAdmin: (context) =>
            const IndicatorBankAdminScreen(),
        AppRoutes.userAnalytics: (context) => const UserAnalyticsScreen(),
        AppRoutes.auditTrail: (context) => const AuditTrailScreen(),
        AppRoutes.countries: (context) => const CountriesScreen(),
        AppRoutes.nsStructure: (context) => const NSStructureScreen(),
        AppRoutes.indicatorBank: (context) => const IndicatorBankScreen(),
        AppRoutes.proposeIndicator: (context) => const ProposeIndicatorScreen(),
        AppRoutes.resources: (context) => const ResourcesScreen(),
        AppRoutes.unifiedPlanningDocuments: (context) =>
            const UnifiedPlanningDocumentsScreen(),
        AppRoutes.unifiedPlanningAnalytics: (context) =>
            const UnifiedPlanningAnalyticsScreen(),
        AppRoutes.disaggregationAnalysis: (context) =>
            const DisaggregationAnalysisScreen(),
        AppRoutes.quizGame: (context) => const QuizGameScreen(),
        AppRoutes.leaderboard: (context) => const LeaderboardScreen(),
      };

  static Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    if (settings.name == AppRoutes.aiChat) {
      return PageRouteBuilder<void>(
        settings: settings,
        pageBuilder: (context, animation, secondaryAnimation) =>
            const AiChatScreenWithBottomNav(),
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
      );
    }

    if (settings.name == AppRoutes.webview) {
      final args = WebViewScreenArgs.parse(settings.arguments);
      return MaterialPageRoute(
        settings: settings,
        builder: (context) => WebViewScreen(
          initialUrl: args.initialUrl,
          forceOfflineAssignmentBundle: args.forceOfflineAssignmentBundle,
          offlineAssignmentId: args.offlineAssignmentId,
        ),
      );
    }

    if (settings.name == AppRoutes.pdfViewer) {
      final raw = settings.arguments;
      final map = raw is Map ? Map<String, dynamic>.from(raw) : <String, dynamic>{};
      final url = map['url']?.toString().trim();
      final filePath = map['filePath']?.toString().trim();
      final thumbRaw = map['thumbnailCacheUrl']?.toString();
      final thumbnailCacheUrl = thumbRaw != null && thumbRaw.trim().isNotEmpty
          ? thumbRaw.trim()
          : null;
      final title = map['title']?.toString().trim() ?? 'Document';
      final hasUrl = url != null && url.isNotEmpty;
      final hasFile = filePath != null && filePath.isNotEmpty;
      if (hasUrl == hasFile) {
        return MaterialPageRoute(
          settings: settings,
          builder: (context) => Scaffold(
            appBar: const AppAppBar(title: 'PDF'),
            body: Center(
              child: Text(
                'Invalid PDF viewer arguments (need url or filePath).',
                style: Theme.of(context).textTheme.bodyLarge,
              ),
            ),
          ),
        );
      }
      return MaterialPageRoute(
        settings: settings,
        builder: (context) => PdfViewerScreen(
          title: title,
          url: hasUrl ? url : null,
          localFilePath: hasFile ? filePath : null,
          thumbnailCacheUrl: thumbnailCacheUrl,
        ),
      );
    }

    if (settings.name == AppRoutes.translationEntryDetail) {
      final args = settings.arguments;
      Map<String, dynamic>? map;
      if (args is Map<String, dynamic>) {
        map = args;
      } else if (args is Map) {
        map = Map<String, dynamic>.from(args);
      }
      if (map != null) {
        return MaterialPageRoute<void>(
          settings: settings,
          builder: (context) =>
              TranslationEntryDetailScreen(entry: map!),
        );
      }
      return MaterialPageRoute<void>(
        settings: settings,
        builder: (context) => const Scaffold(
          appBar: AppAppBar(title: 'Error'),
          body: Center(child: Text('Missing translation data.')),
        ),
      );
    }

    // NS structure with country ID: /ns-structure/{id}
    if (settings.name != null &&
        settings.name!.startsWith('/ns-structure/')) {
      final idString = settings.name!.split('/').last;
      final countryId = int.tryParse(idString);
      if (countryId != null) {
        return MaterialPageRoute(
          settings: settings,
          builder: (context) => NSStructureScreen(countryId: countryId),
        );
      }
    }

    // Document detail: /admin/documents/{id} (requires `Document` in arguments)
    if (settings.name != null &&
        settings.name!.startsWith('/admin/documents/')) {
      final parts =
          settings.name!.split('/').where((s) => s.isNotEmpty).toList();
      if (parts.length == 3 &&
          parts[0] == 'admin' &&
          parts[1] == 'documents') {
        final id = int.tryParse(parts[2]);
        if (id != null) {
          final args = settings.arguments;
          Document? document;
          if (args is Document) {
            document = args;
          } else if (args is Map) {
            try {
              document = Document.fromJson(
                Map<String, dynamic>.from(args),
              );
            } catch (_) {
              document = null;
            }
          }
          if (document != null) {
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (context) =>
                  DocumentDetailScreen(document: document!),
            );
          }
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (context) => Scaffold(
              appBar: AppAppBar(
                title: AppLocalizations.of(context)?.indicatorDetailDetails ??
                    'Details',
              ),
              body: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    AppLocalizations.of(context)?.assignmentDetailMissingData ??
                        'Open this item from the list.',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ),
          );
        }
      }
    }

    // Resource detail: /admin/resources/{id} (requires `Resource` in arguments)
    if (settings.name != null &&
        settings.name!.startsWith('/admin/resources/')) {
      final parts =
          settings.name!.split('/').where((s) => s.isNotEmpty).toList();
      if (parts.length == 3 &&
          parts[0] == 'admin' &&
          parts[1] == 'resources') {
        final id = int.tryParse(parts[2]);
        if (id != null) {
          final args = settings.arguments;
          Resource? resource;
          if (args is Resource) {
            resource = args;
          } else if (args is Map) {
            try {
              resource = Resource.fromJson(
                Map<String, dynamic>.from(args),
              );
            } catch (_) {
              resource = null;
            }
          }
          if (resource != null) {
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (context) =>
                  ResourceDetailScreen(resource: resource!),
            );
          }
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (context) => Scaffold(
              appBar: AppAppBar(
                title: AppLocalizations.of(context)?.indicatorDetailDetails ??
                    'Details',
              ),
              body: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    AppLocalizations.of(context)?.assignmentDetailMissingData ??
                        'Open this item from the list.',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ),
          );
        }
      }
    }

    // Assignment detail: /admin/assignments/{id} (requires `AdminAssignment` in arguments)
    if (settings.name != null &&
        settings.name!.startsWith('/admin/assignments/')) {
      final parts = settings.name!.split('/');
      if (parts.length >= 4) {
        final id = int.tryParse(parts[3]);
        if (id != null) {
          final args = settings.arguments;
          AdminAssignment? assignment;
          if (args is AdminAssignment) {
            assignment = args;
          } else if (args is Map) {
            try {
              assignment = AdminAssignment.fromJson(
                Map<String, dynamic>.from(args),
              );
            } catch (_) {
              assignment = null;
            }
          }
          if (assignment != null) {
            return MaterialPageRoute<void>(
              settings: settings,
              builder: (context) =>
                  AssignmentDetailScreen(assignment: assignment!),
            );
          }
          return MaterialPageRoute<void>(
            settings: settings,
            builder: (context) => Scaffold(
              appBar: AppAppBar(
                title: AppLocalizations.of(context)?.assignmentDetails ??
                    'Assignment details',
              ),
              body: Center(
                child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    AppLocalizations.of(context)?.assignmentDetailMissingData ??
                        'Open this assignment from the list.',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ),
          );
        }
      }
    }

    // Indicator detail: /indicator-bank/{id} (not /indicator-bank/propose)
    if (settings.name != null &&
        settings.name!.startsWith('/indicator-bank/') &&
        settings.name != AppRoutes.proposeIndicator) {
      final idString = settings.name!.split('/').last;
      final id = int.tryParse(idString);
      if (id != null) {
        return MaterialPageRoute(
          settings: settings,
          builder: (context) => IndicatorDetailScreen(indicatorId: id),
        );
      }
    }

    // Edit indicator: /admin/indicator_bank/edit/{id}
    if (settings.name != null &&
        settings.name!.startsWith('/admin/indicator_bank/edit/')) {
      final idString = settings.name!.split('/').last;
      final id = int.tryParse(idString);
      if (id != null) {
        return MaterialPageRoute(
          settings: settings,
          builder: (context) => EditIndicatorScreen(indicatorId: id),
        );
      }
    }

    // Edit entity: /admin/organization/edit/{entityType}/{id}
    //           or /admin/organization/edit/{id}
    if (settings.name != null &&
        settings.name!.startsWith('/admin/organization/edit/')) {
      final parts = settings.name!.split('/');
      if (parts.length == 6) {
        final entityType = parts[4];
        final idString = parts[5];
        final id = int.tryParse(idString);
        if (id != null) {
          final args = settings.arguments;
          final entityName =
              args is Map ? args['entityName'] as String? : null;
          return MaterialPageRoute(
            settings: settings,
            builder: (context) => EditEntityScreen(
              entityId: id,
              entityType: entityType,
              entityName: entityName,
            ),
          );
        }
      } else if (parts.length == 5) {
        final idString = parts[4];
        final id = int.tryParse(idString);
        if (id != null) {
          final args = settings.arguments;
          final entityName =
              args is Map ? args['entityName'] as String? : null;
          final entityType =
              args is Map ? args['entityType'] as String? : null;
          return MaterialPageRoute(
            settings: settings,
            builder: (context) => EditEntityScreen(
              entityId: id,
              entityType: entityType,
              entityName: entityName,
            ),
          );
        }
      }
    }

    return null;
  }
}
