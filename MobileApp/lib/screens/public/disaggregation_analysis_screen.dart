import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:provider/provider.dart';
import '../../services/session_service.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../config/app_config.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/url_helper.dart';
import '../../utils/ios_constants.dart';
import '../../services/webview_service.dart';
import '../../l10n/app_localizations.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/ios_button.dart';
import '../../config/routes.dart';
import '../../widgets/webview_pull_to_refresh.dart';

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
  final SessionService _sessionService = SessionService();
  bool _isLoading = true;
  double _progress = 0;
  String? _error;
  bool _webViewInitialized = false;

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
    if (_webViewInitialized) return;

    setState(() {
      _webViewInitialized = true;
    });

    // Inject session in background
    _injectSession();
  }

  Future<void> _injectSession() async {
    await _sessionService.injectSessionIntoWebView();
  }

  String _buildUrl(String language) {
    return UrlHelper.buildFrontendUrlWithLanguage(
        '/disaggregation-analysis', language);
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
        final isStandalone = _isStandaloneScreen(context);
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
          drawer: _buildNavigationDrawer(context, languageProvider, theme, localizations, language),
          body: Stack(
            children: [
              Container(
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
                                  url), // Rebuild WebView when language changes
                              initialUrlRequest: URLRequest(
                                url: WebUri(url),
                                headers: WebViewService.defaultRequestHeaders,
                              ),
                              initialUserScripts:
                                  WebViewService.getRequestInterceptorScripts(
                                      language: language),
                              initialSettings: WebViewService.defaultSettings(),
                              onWebViewCreated: (controller) {
                                _webViewController = controller;
                              },
                            onConsoleMessage: (controller, consoleMessage) {
                              // Suppress console messages from WebView pages, especially syntax errors
                              // Filter out common remote website errors that don't affect app functionality
                              final message = consoleMessage.message.toLowerCase();
                              final shouldIgnore = message.contains('uncaught syntaxerror') ||
                                  message.contains('unexpected identifier') ||
                                  message.contains('uncaught typeerror') ||
                                  message.contains('cannot read properties of null') ||
                                  message.contains('cannot read property') ||
                                  message.contains('scrolltop') ||
                                  message.contains('scroll') ||
                                  message.contains('self');

                              // Suppress all console messages - these are from the remote website
                              // Only log in debug mode if you need to debug WebView issues
                              // if (!shouldIgnore && kDebugMode) {
                              //   print('[DISAGGREGATION WEBVIEW] ${consoleMessage.messageLevel}: ${consoleMessage.message}');
                              // }
                            },
                            shouldOverrideUrlLoading:
                                (controller, navigationAction) async {
                              // Validate URL before loading
                              final url = navigationAction.request.url;
                              if (url != null && !WebViewService.isUrlAllowed(url)) {
                                if (mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    SnackBar(
                                      content: Text(
                                          'Navigation to this URL is not allowed'),
                                      backgroundColor: Theme.of(context)
                                          .colorScheme
                                          .error,
                                    ),
                                  );
                                }
                                return NavigationActionPolicy.CANCEL;
                              }
                              return NavigationActionPolicy.ALLOW;
                            },
                            onLoadStart: (controller, url) {
                              setState(() {
                                _isLoading = true;
                                _error = null;
                              });
                            },
                            onLoadStop: (controller, url) async {
                              setState(() {
                                _isLoading = false;
                                _error = null; // Clear error on successful load
                              });

                              // Inject Tajawal font after page loads if Arabic is selected
                              if (language == 'ar') {
                                await controller.evaluateJavascript(source: '''
                                  (function() {
                                    // Ensure Tajawal font is loaded
                                    const link = document.createElement('link');
                                    link.href = 'https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;700&display=swap';
                                    link.rel = 'stylesheet';
                                    link.crossOrigin = 'anonymous';
                                    if (!document.querySelector('link[href*="Tajawal"]')) {
                                      document.head.appendChild(link);
                                    }

                                    // Apply font with high specificity
                                    const styleId = 'tajawal-font-injection-final';
                                    let style = document.getElementById(styleId);
                                    if (!style) {
                                      style = document.createElement('style');
                                      style.id = styleId;
                                      document.head.appendChild(style);
                                    }
                                    style.textContent = `
                                      * {
                                        font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                                      }
                                      body, html {
                                        font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                                      }
                                      [dir="rtl"], .rtl, [dir="rtl"] *, .rtl * {
                                        font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                                      }
                                      h1, h2, h3, h4, h5, h6, p, span, div, a, button, input, textarea, select, label, li, td, th, .text-base, .text-sm, .text-lg, .text-xl, .text-2xl, .text-3xl, .text-4xl, .text-5xl, .text-6xl {
                                        font-family: 'Tajawal', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif !important;
                                      }
                                    `;
                                  })();
                                ''');
                              }
                            },
                            onProgressChanged: (controller, progress) {
                              setState(() {
                                _progress = progress / 100;
                              });
                            },
                            onReceivedError: (controller, request, error) {
                              if (WebViewService.shouldIgnoreError(
                                  error.description)) {
                                print(
                                    '[DISAGG WEBVIEW] Ignored error: ${error.description}');
                                return;
                              }
                              setState(() {
                                _isLoading = false;
                                _error = error.description;
                              });
                            },
                            onReceivedHttpError:
                                (controller, request, response) {
                              final statusCode = response.statusCode;
                              if (statusCode != null && statusCode >= 400) {
                                setState(() {
                                  _isLoading = false;
                                  _error = 'HTTP Error $statusCode';
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
                                  context.navyBackgroundColor(opacity: 0.05),
                                  theme.scaffoldBackgroundColor,
                                ],
                              ),
                            ),
                            child: Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  CircularProgressIndicator(
                                    valueColor: AlwaysStoppedAnimation<Color>(
                                      Color(AppConstants.ifrcRed),
                                    ),
                                  ),
                                  const SizedBox(height: 16),
                                  Text(
                                    localizations.loadingHome,
                                    style: const TextStyle(
                                      color: Color(AppConstants.textSecondary),
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
                                    color: const Color(AppConstants.errorColor)
                                        .withOpacity(0.1),
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
                                        .withOpacity(0.6),
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
                                    backgroundColor:
                                        Color(AppConstants.ifrcRed),
                                    foregroundColor:
                                        theme.colorScheme.onPrimary,
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 24,
                                      vertical: 12,
                                    ),
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(12),
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
                  currentIndex: 2, // Home tab highlighted
                  onTap: (index) {
                    // Navigate back to main navigation screen
                    Navigator.of(context).popUntil((route) {
                      return route.isFirst ||
                          route.settings.name == AppRoutes.dashboard;
                    });
                  },
                )
              : null,
        );
      },
    );
  }

  Widget _buildNavigationDrawer(BuildContext context, LanguageProvider languageProvider, ThemeData theme, AppLocalizations localizations, String language) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAdmin = user != null && (user.role == 'admin' || user.role == 'system_manager');
    final isAuthenticated = authProvider.isAuthenticated;
    final isFocalPoint = user != null && user.role == 'focal_point';
    final isDark = theme.brightness == Brightness.dark;

    return Drawer(
      backgroundColor: isDark
          ? IOSColors.secondarySystemBackgroundDark
          : IOSColors.systemBackground,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.zero,
      ),
      child: SafeArea(
        child: Column(
          children: [
            // Title
            Padding(
              padding: const EdgeInsets.fromLTRB(
                IOSSpacing.xl,
                IOSSpacing.lg,
                IOSSpacing.xl,
                IOSSpacing.md,
              ),
              child: Text(
                localizations.navigation,
                style: IOSTextStyle.title2(context),
              ),
            ),
            // Scrollable menu items
            Expanded(
              child: ListView(
                padding: EdgeInsets.zero,
                children: [
                  // Menu items
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.home,
                    title: localizations.home ?? 'Global Overview',
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).popUntil((route) {
                        return route.isFirst || route.settings.name == AppRoutes.dashboard;
                      });
                    },
                  ),
                  // Indicator Bank - navigate to native Indicator Bank screen
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.library_books,
                    title: localizations.indicatorBank,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
                      Navigator.of(context).pushNamed(AppRoutes.indicatorBank);
                    },
                  ),
                  // Quiz Game - navigate to quiz game screen
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.quiz,
                    title: localizations.quizGame,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pushNamed(
                        AppRoutes.quizGame,
                      );
                    },
                  ),
                  // AI Assistant (ChatGPT-like native chat)
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.smart_toy_outlined,
                    title: 'AI Assistant',
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pushNamed(AppRoutes.aiChat);
                    },
                  ),
                  // Resources/Notifications - navigate to native screen
                  if (isFocalPoint)
                    _buildMenuTile(
                      context: context,
                      theme: theme,
                      icon: Icons.notifications,
                      title: localizations.notifications ?? 'Notifications',
                      onTap: () {
                        Navigator.pop(context);
                        Navigator.of(context).pop();
                        Navigator.of(context).pushNamed(AppRoutes.notifications);
                      },
                    )
                  else
                    _buildMenuTile(
                      context: context,
                      theme: theme,
                      icon: Icons.folder,
                      title: localizations.resources ?? 'Resources',
                      onTap: () {
                        Navigator.pop(context);
                        Navigator.of(context).pop();
                        Navigator.of(context).pushNamed(AppRoutes.resources);
                      },
                    ),
                  // Countries - show in bottom sheet
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.public,
                    title: localizations.countries,
                    onTap: () {
                      Navigator.pop(context);
                      _showCountriesSheet(context, theme);
                    },
                  ),
                  // Analysis section header
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      IOSSpacing.xl,
                      IOSSpacing.lg,
                      IOSSpacing.xl,
                      IOSSpacing.sm,
                    ),
                    child: Text(
                      localizations.analysis.toUpperCase(),
                      style: IOSTextStyle.footnote(context).copyWith(
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  // Disaggregation Analysis - already here, just pop drawer
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.analytics,
                    title: localizations.disaggregationAnalysis,
                    onTap: () {
                      Navigator.pop(context);
                      // Already on Disaggregation Analysis screen
                    },
                  ),
                  // Data Visualization - use webview (no native screen)
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.bar_chart,
                    title: localizations.dataVisualization,
                    showDivider: false,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
                      final fullUrl = UrlHelper.buildFrontendUrlWithLanguage('/dataviz', language);
                      Navigator.of(context).pushNamed(
                        AppRoutes.webview,
                        arguments: fullUrl,
                      );
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
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.9,
          ),
          decoration: BoxDecoration(
            color: theme.scaffoldBackgroundColor,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
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
                        tooltip: localizations.close ?? 'Close',
                        semanticLabel: localizations.close ?? 'Close',
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                // Countries widget
                Expanded(
                  child: const CountriesWidget(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMenuTile({
    required BuildContext context,
    required ThemeData theme,
    required IconData icon,
    required String title,
    required VoidCallback onTap,
    bool showDivider = true,
  }) {
    final isDark = theme.brightness == Brightness.dark;

    return Column(
      children: [
        InkWell(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: IOSSpacing.xl,
              vertical: IOSSpacing.md,
            ),
            child: Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: IOSColors.getSystemBlue(context).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(
                    icon,
                    color: IOSColors.getSystemBlue(context),
                    size: 18,
                  ),
                ),
                const SizedBox(width: IOSSpacing.md),
                Expanded(
                  child: Text(
                    title,
                    style: IOSTextStyle.body(context),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (showDivider)
          Divider(
            height: 1,
            thickness: 0.5,
            indent: IOSSpacing.xl,
            endIndent: 0,
            color: theme.dividerColor.withOpacity(0.3),
          ),
      ],
    );
  }
}
