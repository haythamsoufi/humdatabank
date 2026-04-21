import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:provider/provider.dart';
import '../../services/session_service.dart';
import '../../di/service_locator.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/url_helper.dart';
import '../../utils/navigation_helper.dart';
import '../../utils/ios_constants.dart';
import '../../utils/debug_logger.dart' show DebugLogger, LogLevel;
import '../../services/webview_service.dart';
import '../../l10n/app_localizations.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/ios_button.dart';
import '../../config/routes.dart';
import '../../models/shared/ai_chat_launch_args.dart';
import '../../widgets/webview_pull_to_refresh.dart';
import '../../widgets/modern_navigation_drawer.dart';

class DisaggregationAnalysisScreen extends StatefulWidget {
  const DisaggregationAnalysisScreen({super.key});

  @override
  State<DisaggregationAnalysisScreen> createState() =>
      _DisaggregationAnalysisScreenState();
}

class _DisaggregationAnalysisScreenState
    extends State<DisaggregationAnalysisScreen>
    with AutomaticKeepAliveClientMixin {
  InAppWebViewController? _webViewController;
  final SessionService _sessionService = sl<SessionService>();
  bool _isLoading = true;
  double _progress = 0;
  String? _error;
  bool _webViewInitialized = false;
  bool _webViewInitInFlight = false;
  bool _arabicFontReinforcedThisLoad = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    // Defer WebView initialization to prevent blocking main thread during app startup
    // Stagger initialization to prevent all WebViews from loading at once
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        // Delay this WebView initialization to stagger across screens
        Future.delayed(const Duration(milliseconds: 350), () {
          if (mounted) {
            _initializeWebView();
          }
        });
      }
    });
  }

  @override
  void dispose() {
    // Dispose WebView controller to free memory
    if (_webViewController != null) {
      _webViewController!.stopLoading();
      _webViewController = null;
    }
    super.dispose();
  }

  Future<void> _initializeWebView() async {
    if (_webViewInitialized || _webViewInitInFlight) return;
    _webViewInitInFlight = true;
    await _injectSession();
    if (!mounted) {
      _webViewInitInFlight = false;
      return;
    }
    setState(() {
      _webViewInitialized = true;
      _webViewInitInFlight = false;
    });
  }

  Future<void> _injectSession() async {
    await _sessionService.injectSessionIntoWebView();
  }

  String _buildUrl(String language) {
    return UrlHelper.buildFrontendUrlWithLanguage(
      '/disaggregation-analysis',
      language,
    );
  }

  bool _isStandaloneScreen(BuildContext context) {
    // Check if this screen is navigated to directly (not as a tab in MainNavigationScreen)
    // When used as a tab, it's embedded in MainNavigationScreen (route name is dashboard or null)
    // When navigated directly via pushNamed, it has a route name matching AppRoutes.disaggregationAnalysis

    final route = ModalRoute.of(context);
    final routeName = route?.settings.name;

    // If route name matches this screen's route exactly, we're definitely standalone
    if (routeName == AppRoutes.disaggregationAnalysis) {
      return true;
    }

    // If route name is null or dashboard, we're a tab (embedded in MainNavigationScreen)
    // MainNavigationScreen wraps tabs and has its own bottomNavigationBar
    if (routeName == null || routeName == AppRoutes.dashboard) {
      return false;
    }

    // For any other route name, check if we can pop
    // If we can pop, we were navigated to directly (standalone)
    // If we can't pop, we're at the root (likely a tab)
    return Navigator.of(context).canPop();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // Required for AutomaticKeepAliveClientMixin
    return Consumer2<AuthProvider, LanguageProvider>(
      builder: (context, authProvider, languageProvider, child) {
        final language = languageProvider.currentLanguage;
        final url = _buildUrl(language);
        final localizations = AppLocalizations.of(context)!;
        final theme = Theme.of(context);
        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: localizations.disaggregationAnalysis,
            leading: Builder(
              builder: (BuildContext scaffoldContext) {
                return IOSIconButton(
                  icon: Icons.menu,
                  onPressed: () {
                    Scaffold.of(scaffoldContext).openDrawer();
                  },
                  tooltip: localizations.navigation,
                  semanticLabel: localizations.navigation,
                  semanticHint: localizations.navigation,
                );
              },
            ),
          ),
          drawer: _buildNavigationDrawer(
            context,
            languageProvider,
            theme,
            localizations,
            language,
          ),
          body: Stack(
            children: [
              ColoredBox(
                color: theme.scaffoldBackgroundColor,
                child: SafeArea(
                  top: true,
                  bottom: false,
                  child: Stack(
                    children: [
                      // WebView container with pull-to-refresh - handles its own scrolling
                      Positioned.fill(
                        child: _webViewInitialized
                            ? WebViewPullToRefresh(
                                webViewController: _webViewController,
                                onRefresh: () async {
                                  // Reload the WebView
                                  _webViewController?.reload();
                                },
                                color: Color(AppConstants.ifrcRed),
                                child: InAppWebView(
                                  key: ValueKey(
                                    url,
                                  ), // Rebuild WebView when language changes
                                  initialUrlRequest: URLRequest(
                                    url: WebUri(url),
                                    headers:
                                        WebViewService.defaultRequestHeaders,
                                  ),
                                  initialUserScripts:
                                      WebViewService.getRequestInterceptorScripts(
                                        language: language,
                                      ),
                                  initialSettings:
                                      WebViewService.defaultSettings(),
                                  onWebViewCreated: (controller) {
                                    _webViewController = controller;
                                  },
                                  onConsoleMessage: (controller, consoleMessage) {
                                    // Remote site console noise suppressed intentionally.
                                  },
                                  shouldOverrideUrlLoading:
                                      (controller, navigationAction) async {
                                        final requestUri =
                                            navigationAction.request.url;
                                        if (requestUri != null &&
                                            !WebViewService.isUrlAllowed(
                                              requestUri,
                                            )) {
                                          if (mounted) {
                                            ScaffoldMessenger.of(
                                              context,
                                            ).showSnackBar(
                                              SnackBar(
                                                content: Text(
                                                  AppLocalizations.of(
                                                    context,
                                                  )!.navUrlNotAllowed,
                                                ),
                                                backgroundColor: Theme.of(
                                                  context,
                                                ).colorScheme.error,
                                              ),
                                            );
                                          }
                                          return NavigationActionPolicy.CANCEL;
                                        }
                                        return NavigationActionPolicy.ALLOW;
                                      },
                                  onLoadStart: (controller, startedUrl) {
                                    setState(() {
                                      _isLoading = true;
                                      _error = null;
                                      _arabicFontReinforcedThisLoad = false;
                                    });
                                  },
                                  onLoadStop: (controller, stoppedUrl) async {
                                    setState(() {
                                      _isLoading = false;
                                      _error = null;
                                    });

                                    if (language == 'ar' &&
                                        !_arabicFontReinforcedThisLoad) {
                                      _arabicFontReinforcedThisLoad = true;
                                      await controller.evaluateJavascript(
                                        source: WebViewService
                                            .arabicTajawalPostLoadEvaluateSource,
                                      );
                                    }
                                  },
                                  onProgressChanged: (controller, progress) {
                                    setState(() {
                                      _progress = progress / 100;
                                    });
                                  },
                                  onReceivedError: (controller, request, error) {
                                    if (WebViewService.shouldIgnoreError(
                                      error.description,
                                    )) {
                                      DebugLogger.log(
                                        'DISAGG_WEBVIEW',
                                        'Ignored error: ${error.description}',
                                        level: LogLevel.debug,
                                      );
                                      return;
                                    }
                                    setState(() {
                                      _isLoading = false;
                                      _error = error.description;
                                    });
                                  },
                                  onReceivedHttpError:
                                      (controller, request, response) {
                                        if (request.isForMainFrame != true) {
                                          return;
                                        }
                                        final statusCode = response.statusCode;
                                        if (statusCode != null &&
                                            statusCode >= 400) {
                                          setState(() {
                                            _isLoading = false;
                                            _error = AppLocalizations.of(
                                              context,
                                            )!.httpError(statusCode);
                                          });
                                        }
                                      },
                                ),
                              )
                            : Container(
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                    colors: [
                                      context.navyBackgroundColor(
                                        opacity: 0.05,
                                      ),
                                      theme.scaffoldBackgroundColor,
                                    ],
                                  ),
                                ),
                                child: Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      CircularProgressIndicator(
                                        valueColor:
                                            AlwaysStoppedAnimation<Color>(
                                              Color(AppConstants.ifrcRed),
                                            ),
                                      ),
                                      const SizedBox(height: 16),
                                      Text(
                                        localizations.loadingHome,
                                        style: const TextStyle(
                                          color: Color(
                                            AppConstants.textSecondary,
                                          ),
                                          fontSize: 14,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                      ),
                      // Loading Indicator
                      if (_webViewInitialized && _isLoading && _progress < 1.0)
                        Positioned(
                          top: 0,
                          left: 0,
                          right: 0,
                          child: Column(
                            children: [
                              LinearProgressIndicator(
                                value: _progress,
                                backgroundColor: context.dividerColor,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  Color(AppConstants.ifrcRed),
                                ),
                                minHeight: 3,
                              ),
                            ],
                          ),
                        ),
                      // Error Display
                      if (_error != null && !_isLoading)
                        Positioned.fill(
                          child: Container(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                begin: Alignment.topCenter,
                                end: Alignment.bottomCenter,
                                colors: [
                                  context.navyBackgroundColor(opacity: 0.05),
                                  theme.scaffoldBackgroundColor,
                                ],
                              ),
                            ),
                            child: Center(
                              child: Padding(
                                padding: const EdgeInsets.all(24),
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Container(
                                      padding: const EdgeInsets.all(20),
                                      decoration: BoxDecoration(
                                        color: const Color(
                                          AppConstants.errorColor,
                                        ).withValues(alpha: 0.1),
                                        shape: BoxShape.circle,
                                      ),
                                      child: const Icon(
                                        Icons.error_outline,
                                        size: 64,
                                        color: Color(AppConstants.errorColor),
                                      ),
                                    ),
                                    const SizedBox(height: 24),
                                    Text(
                                      localizations.oopsSomethingWentWrong,
                                      style: TextStyle(
                                        fontSize: 20,
                                        fontWeight: FontWeight.bold,
                                        color: theme.colorScheme.onSurface,
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      _error!,
                                      style: TextStyle(
                                        color: theme.colorScheme.onSurface
                                            .withValues(alpha: 0.6),
                                        fontSize: 14,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                    const SizedBox(height: 24),
                                    ElevatedButton.icon(
                                      onPressed: () {
                                        setState(() {
                                          _error = null;
                                        });
                                        _webViewController?.reload();
                                      },
                                      icon: const Icon(Icons.refresh),
                                      label: Text(localizations.retry),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Color(
                                          AppConstants.ifrcRed,
                                        ),
                                        foregroundColor:
                                            theme.colorScheme.onPrimary,
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 24,
                                          vertical: 12,
                                        ),
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(
                                            12,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          bottomNavigationBar: _isStandaloneScreen(context)
              ? AppBottomNavigationBar(
                  // Aligns with MainNavigationScreen default tab index (home).
                  currentIndex: 2,
                  onTap: (index) {
                    NavigationHelper.popToMainThenOpenAiIfNeeded(
                      context,
                      index,
                    );
                  },
                )
              : null,
        );
      },
    );
  }

  Widget _buildNavigationDrawer(
    BuildContext context,
    LanguageProvider languageProvider,
    ThemeData theme,
    AppLocalizations localizations,
    String language,
  ) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAuthenticated = authProvider.isAuthenticated;
    final isFocalPoint = user?.isFocalPoint ?? false;

    return Drawer(
      backgroundColor: theme.colorScheme.surface,
      elevation: 1,
      shadowColor: Colors.black.withValues(alpha: 0.1),
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
                  ? () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
                      Navigator.of(context).pushNamed(AppRoutes.settings);
                    }
                  : null,
              profileTapSemanticLabel: localizations.settings,
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.only(bottom: IOSSpacing.lg),
                children: [
                  ModernDrawerTile(
                    icon: Icons.home_rounded,
                    title: localizations.home,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).popUntil((route) {
                        return route.isFirst ||
                            route.settings.name == AppRoutes.dashboard;
                      });
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.library_books_rounded,
                    title: localizations.indicatorBank,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
                      Navigator.of(context).pushNamed(AppRoutes.indicatorBank);
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.quiz_rounded,
                    title: localizations.quizGame,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pushNamed(AppRoutes.quizGame);
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.smart_toy_outlined,
                    title: localizations.aiAssistant,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pushNamed(
                        AppRoutes.aiChat,
                        arguments: AiChatLaunchArgs(
                          bottomNavTabIndex:
                              NavigationHelper.aiChatMainTabPageIndex(context),
                        ),
                      );
                    },
                  ),
                  if (isFocalPoint)
                    ModernDrawerTile(
                      icon: Icons.notifications_rounded,
                      title: localizations.notifications,
                      onTap: () {
                        Navigator.pop(context);
                        Navigator.of(context).pop();
                        Navigator.of(
                          context,
                        ).pushNamed(AppRoutes.notifications);
                      },
                    )
                  else
                    ModernDrawerTile(
                      icon: Icons.folder_rounded,
                      title: localizations.resources,
                      onTap: () {
                        Navigator.pop(context);
                        Navigator.of(context).pop();
                        Navigator.of(context).pushNamed(AppRoutes.resources);
                      },
                    ),
                  ModernDrawerTile(
                    icon: Icons.public_rounded,
                    title: localizations.countries,
                    onTap: () {
                      Navigator.pop(context);
                      _showCountriesSheet(context, theme);
                    },
                  ),
                  ModernDrawerSectionTitle(
                    label: localizations.analysis.toUpperCase(),
                  ),
                  ModernDrawerTile(
                    icon: Icons.analytics_rounded,
                    title: localizations.disaggregationAnalysis,
                    onTap: () {
                      Navigator.pop(context);
                    },
                  ),
                  ModernDrawerTile(
                    icon: Icons.bar_chart_rounded,
                    title: localizations.dataVisualization,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
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

  void _showCountriesSheet(BuildContext context, ThemeData theme) {
    final localizations = AppLocalizations.of(context)!;
    final sheetHeight = MediaQuery.sizeOf(context).height * 0.9;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return SizedBox(
          height: sheetHeight,
          child: Container(
            decoration: BoxDecoration(
              color: theme.scaffoldBackgroundColor,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(20),
              ),
            ),
            child: SafeArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Handle bar
                  Container(
                    margin: const EdgeInsets.only(
                      top: IOSSpacing.md - 4,
                      bottom: IOSSpacing.sm,
                    ),
                    width: 40,
                    height: 4,
                    decoration: BoxDecoration(
                      color: theme.dividerColor,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                  // Title
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: IOSSpacing.xl,
                      vertical: IOSSpacing.md,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text(
                          localizations.countries,
                          style: theme.textTheme.titleLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                        IOSIconButton(
                          icon: Icons.close,
                          onPressed: () => Navigator.pop(bottomSheetContext),
                          tooltip: localizations.close,
                          semanticLabel: localizations.close,
                        ),
                      ],
                    ),
                  ),
                  const Divider(height: 1),
                  const Expanded(child: CountriesWidget()),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}
