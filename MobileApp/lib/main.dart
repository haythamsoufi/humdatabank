import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';
import 'config/routes.dart';
import 'config/app_config.dart';
import 'l10n/app_localizations.dart';
import 'utils/debug_logger.dart';
// Shared providers
import 'providers/shared/auth_provider.dart';
import 'services/auth_service.dart';
import 'providers/shared/dashboard_provider.dart';
import 'providers/shared/notification_provider.dart';
import 'providers/shared/language_provider.dart';
import 'providers/shared/theme_provider.dart';
import 'providers/shared/offline_provider.dart';
// Admin providers
import 'providers/admin/templates_provider.dart';
import 'providers/admin/assignments_provider.dart';
import 'providers/admin/admin_dashboard_provider.dart';
import 'providers/admin/document_management_provider.dart';
import 'providers/admin/translation_management_provider.dart';
import 'providers/admin/resources_management_provider.dart';
import 'providers/admin/organizational_structure_provider.dart';
import 'providers/admin/indicator_bank_admin_provider.dart';
import 'providers/admin/user_analytics_provider.dart';
import 'providers/admin/audit_trail_provider.dart';
import 'providers/public/indicator_bank_provider.dart';
import 'providers/public/quiz_game_provider.dart';
import 'providers/public/leaderboard_provider.dart';
import 'providers/shared/ai_chat_provider.dart';
// Shared screens
import 'screens/shared/login_screen.dart';
import 'screens/shared/azure_login_screen.dart';
import 'screens/shared/dashboard_screen.dart';
import 'screens/shared/settings_screen.dart';
import 'screens/shared/notifications_screen.dart';
import 'screens/shared/splash_screen.dart';
// Public screens
import 'screens/public/webview_screen.dart';
import 'screens/public/home_screen.dart';
import 'screens/public/indicator_bank_screen.dart';
import 'screens/public/indicator_detail_screen.dart';
import 'screens/public/resources_screen.dart';
import 'screens/public/disaggregation_analysis_screen.dart';
import 'screens/public/countries_screen.dart';
import 'screens/public/ns_structure_screen.dart';
import 'screens/public/quiz_game_screen.dart';
import 'screens/public/leaderboard_screen.dart';
import 'screens/shared/ai_chat_screen.dart';
import 'screens/shared/ai_conversations_screen.dart';
// Admin screens
import 'screens/admin/templates_screen.dart';
import 'screens/admin/assignments_screen.dart';
import 'screens/admin/admin_screen.dart';
import 'screens/admin/admin_dashboard_screen.dart';
import 'screens/admin/document_management_screen.dart';
import 'screens/admin/translation_management_screen.dart';
import 'screens/admin/resources_management_screen.dart';
import 'screens/admin/organizational_structure_screen.dart';
import 'screens/admin/indicator_bank_admin_screen.dart';
import 'screens/admin/edit_indicator_screen.dart';
import 'screens/admin/edit_entity_screen.dart';
import 'screens/admin/user_analytics_screen.dart';
import 'screens/admin/audit_trail_screen.dart';
import 'services/storage_service.dart';
import 'services/push_notification_service.dart';
import 'services/auth_error_handler.dart';
import 'services/connectivity_service.dart';
import 'services/performance_service.dart';
import 'services/api_service.dart';
import 'services/organization_config_service.dart';
import 'utils/theme.dart';
import 'utils/responsive_typography.dart';
import 'widgets/admin_drawer.dart';
import 'widgets/bottom_navigation_bar.dart';
import 'widgets/horizontal_swipe_page_view.dart';
import 'widgets/offline_indicator.dart';
import 'widgets/session_expiration_warning.dart';
import 'dart:io' show Platform;
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
// Sentry import - use prefix to avoid conflicts
import 'package:sentry_flutter/sentry_flutter.dart' as sentry;

void main() async {
  // Initialize performance monitoring first
  final performanceService = PerformanceService();
  performanceService.recordAppStart();
  performanceService.recordMainStart();

  WidgetsFlutterBinding.ensureInitialized();

  // Load environment variables (e.g., MOBILE_NOTIFICATION_API_KEY)
  await dotenv.load(fileName: '.env', isOptional: true);

  // Initialize organization configuration
  // Check for ORGANIZATION_CONFIG environment variable or use default
  const organizationConfig = String.fromEnvironment('ORGANIZATION_CONFIG', defaultValue: '');
  await OrganizationConfigService().loadConfig(
    organization: organizationConfig.isNotEmpty ? organizationConfig : null,
  );
  DebugLogger.logInfo('INIT',
      'Organization config loaded: ${OrganizationConfigService().config.organization.name}');

  // Initialize performance service
  await performanceService.initialize();
  performanceService.startInit('binding_initialized');
  performanceService.endInit('binding_initialized');

  // Optimize startup: Initialize critical services in parallel
  // Firebase can be initialized in background (non-blocking for app startup)
  performanceService.startInit('critical_services');

  // Initialize storage and connectivity services in parallel (critical for app)
  final initFutures = <Future>[];

  // Storage service - critical for app state persistence
  initFutures.add(performanceService.trackOperation('storage_init', () async {
    try {
      await StorageService().init();
      DebugLogger.logInfo('INIT', 'Storage service initialized successfully');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to initialize storage service: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }));

  // Connectivity service - critical for offline detection
  initFutures
      .add(performanceService.trackOperation('connectivity_init', () async {
    try {
      await ConnectivityService().initialize();
      DebugLogger.logInfo(
          'INIT', 'Connectivity service initialized successfully');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to initialize connectivity service: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }));

  // Wait for critical services to initialize
  await Future.wait(initFutures);
  performanceService.endInit('critical_services');

  // Set up API service language header interceptor once at app startup
  // This ensures all API requests include the Accept-Language header
  // Must be done before runApp() to ensure it's ready for any early API calls
  final apiService = ApiService();
  apiService.addRequestInterceptor(_languageHeaderInterceptor);
  DebugLogger.logInfo('INIT', 'Language header interceptor added to API service');

  // Initialize Firebase in background (non-blocking for app startup)
  // Push notifications will work once Firebase finishes initializing
  performanceService.startInit('firebase_init');
  // Don't await - let it initialize in background
  performanceService.trackOperation('firebase_init', () async {
    try {
      await Firebase.initializeApp();
      DebugLogger.logInfo('INIT', 'Firebase initialized successfully');
    } catch (e, stackTrace) {
      // Firebase initialization failed - push notifications won't work
      // Log the error but don't crash the app
      DebugLogger.logError('Failed to initialize Firebase: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    } finally {
      performanceService.endInit('firebase_init');
    }
  }).catchError((e) {
    DebugLogger.logError('Firebase initialization error: $e');
    performanceService.endInit('firebase_init');
  });

  // Note: Push notifications will be initialized after user login
  // (Device registration requires authentication)

  // Initialize Sentry if DSN is configured
  if (AppConfig.sentryDsn.isNotEmpty) {
    try {
      await sentry.SentryFlutter.init(
        (options) {
          options.dsn = AppConfig.sentryDsn;
          // Set release version
          options.release = '${AppConfig.appName}@1.0.0+1';
          // Enable automatic breadcrumbs
          options.enableAutoPerformanceTracing = true;
          // Set environment
          options.environment = AppConfig.isStaging
              ? 'staging'
              : (AppConfig.isProduction ? 'production' : 'development');
        },
        appRunner: () {
          runApp(const MyApp());
        },
      );
    } catch (e) {
      // Sentry initialization failed - run app without it
      DebugLogger.logError('Failed to initialize Sentry: $e');
      DebugLogger.logInfo('INIT', 'Running app without Sentry');
      runApp(const MyApp());
    }
  } else {
    // Run app without Sentry if DSN is not configured
    DebugLogger.logInfo('INIT', 'Sentry disabled (DSN not configured)');
    runApp(const MyApp());
  }
}

// Language header interceptor for API requests
// This ensures all API requests include the Accept-Language header
// Reads language from storage dynamically on each request
Future<Map<String, String>> _languageHeaderInterceptor(
    Map<String, String> headers, String endpoint) async {
  try {
    final storage = StorageService();
    final languageCode =
        await storage.getString('selected_language') ?? 'en';
    headers['Accept-Language'] = languageCode;
  } catch (e) {
    // If we can't get the language, default to English
    headers['Accept-Language'] = 'en';
  }
  return headers;
}

class MyApp extends StatefulWidget {
  const MyApp({super.key});

  // Create a global navigator key for push notification navigation
  static final GlobalKey<NavigatorState> navigatorKey =
      GlobalKey<NavigatorState>();

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    // Listen to app lifecycle changes
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    // Remove lifecycle observer
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    // IMPROVED: Refresh session when app resumes from background
    // This ensures users don't return to expired sessions
    if (state == AppLifecycleState.resumed) {
      DebugLogger.logAuth('App resumed - refreshing session...');
      // Refresh session in background
      // Get auth provider from context if available, otherwise use service directly
      final authService = AuthService();
      authService.refreshSession().then((success) {
        if (success) {
          DebugLogger.logAuth('Session refreshed successfully on app resume');
        } else {
          DebugLogger.logWarn('AUTH', 'Session refresh failed on app resume');
        }
      }).catchError((e) {
        DebugLogger.logWarn('AUTH', 'Error refreshing session on app resume: $e');
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    // Track first frame rendering
    WidgetsBinding.instance.addPostFrameCallback((_) {
      PerformanceService().recordFirstFrame();

      // Log performance summary after first frame
      Future.delayed(const Duration(seconds: 1), () async {
        final summary = await PerformanceService().getSummary();
        summary.logSummary();
      });
    });

    return MultiProvider(
      providers: [
        // Core providers - Always needed at app startup
        // These providers manage essential app state and are lightweight
        ChangeNotifierProvider(create: (_) {
          final authProvider = AuthProvider();
          // Set auth provider reference in error handler
          AuthErrorHandler().setAuthProvider(authProvider);
          return authProvider;
        }),
        ChangeNotifierProvider(create: (_) => DashboardProvider()),
        ChangeNotifierProvider(create: (_) => NotificationProvider()),
        ChangeNotifierProvider(create: (_) => LanguageProvider()),
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
        ChangeNotifierProvider(create: (_) {
          final offlineProvider = OfflineProvider();
          // Initialize offline provider asynchronously (non-blocking)
          final performanceService = PerformanceService();
          performanceService.startInit('offline_provider');
          offlineProvider.initialize().then((_) {
            performanceService.endInit('offline_provider');
          }).catchError((e) {
            DebugLogger.logError('Offline provider initialization error: $e');
            performanceService.endInit('offline_provider');
          });
          return offlineProvider;
        }),
        ChangeNotifierProvider(create: (_) => IndicatorBankProvider()),
        ChangeNotifierProvider(create: (_) => LeaderboardProvider()),
        ChangeNotifierProvider(create: (_) => AiChatProvider()),
        ChangeNotifierProxyProvider<IndicatorBankProvider, QuizGameProvider>(
          create: (_) {
            final indicatorProvider = Provider.of<IndicatorBankProvider>(_, listen: false);
            final languageProvider = Provider.of<LanguageProvider>(_, listen: false);
            final quizProvider = QuizGameProvider(indicatorProvider);
            quizProvider.updateLanguageProvider(languageProvider);
            return quizProvider;
          },
          update: (_, indicatorProvider, previous) {
            final languageProvider = Provider.of<LanguageProvider>(_, listen: false);
            if (previous == null) {
              final quizProvider = QuizGameProvider(indicatorProvider);
              quizProvider.updateLanguageProvider(languageProvider);
              return quizProvider;
            }
            previous.updateIndicatorBankProvider(indicatorProvider);
            previous.updateLanguageProvider(languageProvider);
            return previous;
          },
        ),

        // Admin providers - Only actively used when admin screens are accessed
        // These providers are lightweight at creation (data loaded on-demand via load* methods)
        // Using ChangeNotifierProvider ensures automatic disposal when app is removed from tree
        // Note: Providers persist for app lifetime but don't consume resources until first use
        ChangeNotifierProvider(create: (_) => TemplatesProvider()),
        ChangeNotifierProvider(create: (_) => AssignmentsProvider()),
        ChangeNotifierProvider(create: (_) => AdminDashboardProvider()),
        ChangeNotifierProvider(create: (_) => DocumentManagementProvider()),
        ChangeNotifierProvider(create: (_) => TranslationManagementProvider()),
        ChangeNotifierProvider(create: (_) => ResourcesManagementProvider()),
        ChangeNotifierProvider(
            create: (_) => OrganizationalStructureProvider()),
        ChangeNotifierProvider(create: (_) => IndicatorBankAdminProvider()),
        ChangeNotifierProvider(create: (_) => UserAnalyticsProvider()),
        ChangeNotifierProvider(create: (_) => AuditTrailProvider()),
      ],
      child: Consumer2<LanguageProvider, ThemeProvider>(
        builder: (context, languageProvider, themeProvider, child) {
          // Convert language code to Locale
          final locale = Locale(languageProvider.currentLanguage);


          // Set navigator key for push notification service
          PushNotificationService().setNavigatorKey(MyApp.navigatorKey);

          return SessionExpirationWarning(
            child: MaterialApp(
            navigatorKey: MyApp.navigatorKey,
            title: AppConfig.appName,
            debugShowCheckedModeBanner: false,
            theme: AppTheme.lightTheme(locale: locale),
            darkTheme: AppTheme.darkTheme(locale: locale),
            themeMode: themeProvider.themeMode,
            builder: (context, child) {
              // Apply a small, global typography scale based on screen width.
              // This helps keep text proportions comfortable across phones
              // while still respecting the OS accessibility text size setting.
              final theme = Theme.of(context);
              final factor =
                  ResponsiveTypography.screenTextScaleFactor(context);

              final scaled = theme.copyWith(
                textTheme: theme.textTheme.apply(fontSizeFactor: factor),
                primaryTextTheme:
                    theme.primaryTextTheme.apply(fontSizeFactor: factor),
              );

              return Theme(
                data: scaled,
                child: child ?? const SizedBox.shrink(),
              );
            },
            locale: locale,
            supportedLocales: LanguageProvider.availableLanguages
                .map((lang) => Locale(lang['code']!))
                .toList(),
            localizationsDelegates: const [
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
              AppLocalizations.delegate,
            ],
            initialRoute: AppRoutes.splash,
            routes: {
              AppRoutes.splash: (context) => const SplashScreen(),
              AppRoutes.login: (context) => const LoginScreen(),
              AppRoutes.azureLogin: (context) => const AzureLoginScreen(),
              AppRoutes.dashboard: (context) {
                // Navigate to MainNavigationScreen with dashboard tab (index 1)
                final args = ModalRoute.of(context)?.settings.arguments;
                final tabIndex = args is int
                    ? args
                    : 1; // Default to 1 (Dashboard) for /dashboard route
                return MainNavigationScreen(initialTabIndex: tabIndex);
              },
              AppRoutes.settings: (context) => const SettingsScreen(),
              AppRoutes.notifications: (context) {
                // Navigate to MainNavigationScreen with notifications tab (index 0 for admin/focal point)
                final args = ModalRoute.of(context)?.settings.arguments;
                final tabIndex = args is int
                    ? args
                    : 0; // Default to 0 (Notifications) for /notifications route
                return MainNavigationScreen(initialTabIndex: tabIndex);
              },
              AppRoutes.admin: (context) =>
                  const AdminScreen(showBottomNav: true),
              AppRoutes.adminDashboard: (context) =>
                  const AdminDashboardScreen(showBottomNav: true),
              AppRoutes.templates: (context) => const TemplatesScreen(),
              AppRoutes.assignments: (context) => const AssignmentsScreen(),
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
              AppRoutes.resources: (context) => const ResourcesScreen(),
              AppRoutes.disaggregationAnalysis: (context) => const DisaggregationAnalysisScreen(),
              AppRoutes.quizGame: (context) => const QuizGameScreen(),
              AppRoutes.leaderboard: (context) => const LeaderboardScreen(),
              AppRoutes.aiConversations: (context) => const AiConversationsScreen(),
              AppRoutes.aiChat: (context) => const AiChatScreen(),
            },
            onGenerateRoute: (settings) {
              if (settings.name == AppRoutes.webview) {
                final url = settings.arguments as String;
                return MaterialPageRoute(
                  builder: (context) => WebViewScreen(initialUrl: url),
                );
              }
              // Handle NS structure route with country ID parameter
              if (settings.name != null &&
                  settings.name!.startsWith('/ns-structure/')) {
                final idString = settings.name!.split('/').last;
                final countryId = int.tryParse(idString);
                if (countryId != null) {
                  return MaterialPageRoute(
                    builder: (context) =>
                        NSStructureScreen(countryId: countryId),
                  );
                }
              }
              // Handle indicator detail route with ID parameter
              if (settings.name != null &&
                  settings.name!.startsWith('/indicator-bank/')) {
                final idString = settings.name!.split('/').last;
                final id = int.tryParse(idString);
                if (id != null) {
                  return MaterialPageRoute(
                    builder: (context) =>
                        IndicatorDetailScreen(indicatorId: id),
                  );
                }
              }
              // Handle edit indicator route with ID parameter
              if (settings.name != null &&
                  settings.name!.startsWith('/admin/indicator_bank/edit/')) {
                final idString = settings.name!.split('/').last;
                final id = int.tryParse(idString);
                if (id != null) {
                  return MaterialPageRoute(
                    builder: (context) => EditIndicatorScreen(indicatorId: id),
                  );
                }
              }
              // Handle edit entity route with ID and optional entity type parameter
              if (settings.name != null &&
                  settings.name!.startsWith('/admin/organization/edit/')) {
                final parts = settings.name!.split('/');
                // Route format: /admin/organization/edit/{entityType}/{id} or /admin/organization/edit/{id}
                if (parts.length == 6) {
                  // Has entity type: /admin/organization/edit/{entityType}/{id}
                  final entityType = parts[4];
                  final idString = parts[5];
                  final id = int.tryParse(idString);
                  if (id != null) {
                    // Get entity name from arguments if provided
                    final args = settings.arguments;
                    final entityName =
                        args is Map ? args['entityName'] as String? : null;
                    return MaterialPageRoute(
                      builder: (context) => EditEntityScreen(
                        entityId: id,
                        entityType: entityType,
                        entityName: entityName,
                      ),
                    );
                  }
                } else if (parts.length == 5) {
                  // No entity type: /admin/organization/edit/{id}
                  final idString = parts[4];
                  final id = int.tryParse(idString);
                  if (id != null) {
                    final args = settings.arguments;
                    final entityName =
                        args is Map ? args['entityName'] as String? : null;
                    final entityType =
                        args is Map ? args['entityType'] as String? : null;
                    return MaterialPageRoute(
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
            },
          ),
          )
        ;
        },
      ),
    );
  }
}

class MainNavigationScreen extends StatefulWidget {
  final int? initialTabIndex;

  const MainNavigationScreen({super.key, this.initialTabIndex});

  @override
  State<MainNavigationScreen> createState() => _MainNavigationScreenState();
}

class _MainNavigationScreenState extends State<MainNavigationScreen>
    with WidgetsBindingObserver {
  late int
      _currentIndex; // Will be initialized based on initialTabIndex or default to Home
  final GlobalKey _homeScreenKey = GlobalKey();
  late PageController _pageController;

  // Cache screens to prevent unnecessary rebuilds
  List<Widget>? _cachedScreens;
  bool? _cachedIsAdmin;
  bool? _cachedIsAuthenticated;
  bool? _cachedIsFocalPoint;
  int? _previousScreenCount;

  // Screen caching configuration
  static const int _maxCachedScreens = 5; // Maximum screens to keep cached
  static const int _keepAroundCurrent =
      2; // Keep this many screens around current page
  DateTime? _lastMemoryPressureWarning;
  static const Duration _memoryPressureCooldown = Duration(minutes: 5);

  // Periodic memory cleanup timer (optional - can be enabled if needed)
  // Timer? _memoryCleanupTimer;

  int _getHomeIndex(bool isAdmin, bool isAuthenticated) {
    // Home is always at index 2 for all user types
    return 2;
  }

  List<Widget> _buildScreens(
      bool isAdmin, bool isAuthenticated, bool isFocalPoint) {
    // Check if user type has changed - if so, clear old cached screens
    final userTypeChanged = _cachedScreens != null &&
        (_cachedIsAdmin != isAdmin ||
            _cachedIsAuthenticated != isAuthenticated ||
            _cachedIsFocalPoint != isFocalPoint);

    // Check if we have too many cached screens (memory limit)
    final cachedScreenCount = _cachedScreens?.length ?? 0;
    final hasTooManyScreens = cachedScreenCount > _maxCachedScreens;

    // Clear cached screens if user type changed or too many screens cached
    if ((userTypeChanged || hasTooManyScreens) && _cachedScreens != null) {
      if (userTypeChanged) {
        DebugLogger.logInfo(
            'NAV', 'Clearing cached screens due to user type change');
      } else {
        DebugLogger.logInfo('NAV',
            'Clearing cached screens due to memory limit ($cachedScreenCount > $_maxCachedScreens)');
      }
      _cachedScreens = null;
    }

    // Return cached screens if user type hasn't changed and cache is valid
    if (_cachedScreens != null && !userTypeChanged && !hasTooManyScreens) {
      // Periodically clear distant screens if we're getting close to limit
      if (_cachedScreens!.length >= _maxCachedScreens - 1) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _clearDistantScreens();
          }
        });
      }
      return _cachedScreens!;
    }

    List<Widget> screens;
    if (isAdmin) {
      screens = [
        const NotificationsScreen(), // Index 0
        const DashboardScreen(), // Index 1
        HomeScreen(key: _homeScreenKey), // Index 2 - Home (main screen)
        const AdminDashboardScreen(), // Index 3
        const AdminScreen(), // Index 4
      ];
    } else if (isAuthenticated) {
      // Authenticated non-admin users
      if (isFocalPoint) {
        // Focal points see Notifications instead of Resources
        screens = [
          const NotificationsScreen(), // Index 0 - Notifications (for focal points)
          const DashboardScreen(), // Index 1 - Dashboard (middle)
          HomeScreen(key: _homeScreenKey), // Index 2 - Home
          const DisaggregationAnalysisScreen(), // Index 3
          const SettingsScreen(), // Index 4
        ];
      } else {
        // Other authenticated non-admin users see Resources
        screens = [
          const ResourcesScreen(), // Index 0 - Resources
          const DashboardScreen(), // Index 1 - Dashboard (middle)
          HomeScreen(key: _homeScreenKey), // Index 2 - Home
          const DisaggregationAnalysisScreen(), // Index 3
          const SettingsScreen(), // Index 4
        ];
      }
    } else {
      // Non-authenticated users
      screens = [
        const ResourcesScreen(), // Index 0 - Resources (swapped with Home)
        const IndicatorBankScreen(), // Index 1
        HomeScreen(
            key: _homeScreenKey), // Index 2 - Home (swapped with Resources)
        const DisaggregationAnalysisScreen(), // Index 3
        const SettingsScreen(), // Index 4
      ];
    }

    // Cache the screens
    _cachedScreens = screens;
    _cachedIsAdmin = isAdmin;
    _cachedIsAuthenticated = isAuthenticated;
    _cachedIsFocalPoint = isFocalPoint;

    return screens;
  }

  @override
  void initState() {
    super.initState();
    // Add lifecycle observer for memory pressure handling
    WidgetsBinding.instance.addObserver(this);

    // Initialize currentIndex from widget parameter or default to 2 (Home)
    // This will be adjusted in build() based on user role and screens
    _currentIndex = widget.initialTabIndex ?? 2;
    // Initialize PageController with initial page
    _pageController = PageController(initialPage: _currentIndex);
    // Defer auth check to avoid setState during build
    // Use a small delay to allow UI to render first
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Future.delayed(const Duration(milliseconds: 100), () {
        if (mounted) {
          _checkAuthStatus();
        }
      });
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    super.didChangeAppLifecycleState(state);

    // Clear cached screens when app goes to background to free memory
    // This helps prevent memory issues when app is in background
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      DebugLogger.logInfo('NAV',
          'App going to background - clearing cached screens to free memory');
      _clearDistantScreens();
    } else if (state == AppLifecycleState.resumed) {
      // App resumed - cache will be rebuilt as needed
      DebugLogger.logInfo('NAV', 'App resumed');
    }
  }

  void _handleMemoryPressure() {
    final now = DateTime.now();

    // Rate limit memory pressure handling (don't clear too frequently)
    if (_lastMemoryPressureWarning != null &&
        now.difference(_lastMemoryPressureWarning!) < _memoryPressureCooldown) {
      return;
    }

    _lastMemoryPressureWarning = now;
    DebugLogger.logWarn(
        'NAV', 'Memory pressure detected - clearing cached screens');

    // Clear screens that are far from current page
    _clearDistantScreens();
  }

  void _clearDistantScreens({bool keepOnlyCurrent = false}) {
    if (_cachedScreens == null || _cachedScreens!.isEmpty) return;

    // Clear cached screens to force recreation
    // This will dispose old widgets and free memory
    // Note: PageView requires all children, but clearing cache will force
    // recreation which allows Flutter to dispose old widgets properly
    DebugLogger.logInfo('NAV',
        'Clearing screen cache to free memory (current page: $_currentIndex)');

    setState(() {
      // Clear cache to force recreation - this allows Flutter to dispose old widgets
      _cachedScreens = null;
    });
  }

  @override
  void dispose() {
    // Remove lifecycle observer
    WidgetsBinding.instance.removeObserver(this);

    // Clear cached screens to free memory
    _cachedScreens = null;

    // Dispose page controller
    _pageController.dispose();
    super.dispose();
  }

  Future<void> _checkAuthStatus() async {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    await authProvider.checkAuthStatus();
    // Don't redirect to login - allow non-authenticated users to browse
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;
        final isAdmin = user != null &&
            (user.role == 'admin' || user.role == 'system_manager');
        final isFocalPoint = user != null && user.role == 'focal_point';

        // Note: We don't redirect to login here anymore - allow non-authenticated users to browse
        final isAuthenticated = authProvider.isAuthenticated;

        // Debug logging for navigation screen selection
        DebugLogger.log('NAV', 'Building navigation screens:',
            level: LogLevel.debug);
        DebugLogger.log('NAV', '  - User: ${user?.email ?? "null"}',
            level: LogLevel.debug);
        DebugLogger.log('NAV', '  - Role: ${user?.role ?? "null"}',
            level: LogLevel.debug);
        DebugLogger.log('NAV', '  - isAdmin: $isAdmin', level: LogLevel.debug);
        DebugLogger.log('NAV', '  - isFocalPoint: $isFocalPoint',
            level: LogLevel.debug);
        DebugLogger.log('NAV', '  - isAuthenticated: $isAuthenticated',
            level: LogLevel.debug);

        final screens = _buildScreens(isAdmin, isAuthenticated, isFocalPoint);

        DebugLogger.log('NAV', '  - Screen count: ${screens.length}',
            level: LogLevel.debug);
        DebugLogger.log('NAV',
            '  - Screen types: ${isAdmin ? "Admin" : (isAuthenticated ? "Authenticated" : "Public")}',
            level: LogLevel.debug);

        // Determine default index based on whether initialTabIndex was provided
        // If initialTabIndex was provided (e.g., from navigation), use it; otherwise default to Home
        final defaultHomeIndex = isAdmin ? 2 : (isAuthenticated ? 2 : 2);
        final initialIndex = widget.initialTabIndex ?? defaultHomeIndex;
        // Use initialIndex if it's the first build, otherwise use current index
        final targetIndex = _previousScreenCount == null
            ? (initialIndex < screens.length ? initialIndex : defaultHomeIndex)
            : (_currentIndex < screens.length
                ? _currentIndex
                : defaultHomeIndex);

        // Update _currentIndex if this is first build and we have an initial tab index
        if (_previousScreenCount == null && widget.initialTabIndex != null) {
          _currentIndex = targetIndex;
        }

        final validIndex = targetIndex;

        // Handle screen count changes (when user type changes)
        if (_previousScreenCount != null &&
            _previousScreenCount != screens.length) {
          // Screens changed, need to update controller
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              final newIndex =
                  validIndex < screens.length ? validIndex : defaultHomeIndex;
              _pageController.dispose();
              _pageController = PageController(initialPage: newIndex);
              setState(() {
                _currentIndex = newIndex;
              });
            }
          });
        }
        _previousScreenCount = screens.length;

        // If index was invalid, update it
        if (_currentIndex != validIndex) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted && _pageController.hasClients) {
              _pageController.animateToPage(
                validIndex,
                duration: const Duration(milliseconds: 300),
                curve: Curves.easeInOut,
              );
              setState(() {
                _currentIndex = validIndex;
              });
            }
          });
        }

        return Scaffold(
          backgroundColor: Theme.of(context).scaffoldBackgroundColor,
          body: Column(
            children: [
              // Offline banner at the top
              const OfflineBanner(),
              // Main content
              Expanded(
                child: HorizontalSwipePageView(
                  controller: _pageController,
                  onPageChanged: (index) {
                    // Update current index when user swipes
                    setState(() {
                      _currentIndex = index;
                    });

                    // Periodically clear distant screens when user navigates
                    // This prevents memory buildup from old screens
                    if (_cachedScreens != null &&
                        _cachedScreens!.length > _maxCachedScreens) {
                      WidgetsBinding.instance.addPostFrameCallback((_) {
                        if (mounted) {
                          _clearDistantScreens();
                        }
                      });
                    }
                  },
                  children: screens,
                ),
              ),
            ],
          ),
          bottomNavigationBar: AppBottomNavigationBar(
            currentIndex: validIndex,
            onTap: (index) {
              final homeIndex = _getHomeIndex(isAdmin, isAuthenticated);

              // If clicking Home while already on Home, reload it
              if (index == homeIndex && validIndex == homeIndex) {
                HomeScreen.reloadFromKey(_homeScreenKey);
              } else {
                // Animate to the selected page when tapping bottom nav
                if (_pageController.hasClients) {
                  _pageController.animateToPage(
                    index,
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOut,
                  );
                }
                // Update index immediately for bottom nav bar
                setState(() {
                  _currentIndex = index;
                });
              }
            },
            isFocalPoint: isFocalPoint,
          ),
        );
      },
    );
  }
}
