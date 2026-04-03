import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../services/session_service.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/url_helper.dart';
import '../../widgets/admin_drawer.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../services/webview_service.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/debug_logger.dart';

class WebViewScreen extends StatefulWidget {
  final String initialUrl;

  const WebViewScreen({
    super.key,
    required this.initialUrl,
  });

  @override
  State<WebViewScreen> createState() => _WebViewScreenState();
}

class _WebViewScreenState extends State<WebViewScreen> {
  InAppWebViewController? _webViewController;
  final SessionService _sessionService = SessionService();
  bool _isLoading = true;
  double _progress = 0;
  String? _error;
  String? _pageTitle;
  final int _currentNavIndex =
      -1; // -1 means no tab is active (WebView is on top)

  @override
  void initState() {
    super.initState();
    _injectSession();
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

  Future<void> _injectSession() async {
    await _sessionService.injectSessionIntoWebView();
  }

  Future<void> _handleDownload(Uri url) async {
    try {
      // Use platformDefault instead of externalApplication to trigger
      // Android's download manager within the app context
      if (await canLaunchUrl(url)) {
        await launchUrl(url, mode: LaunchMode.platformDefault);
      } else {
        if (mounted) {
          final theme = Theme.of(context);
          final localizations = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.couldNotOpenDownloadLink),
              backgroundColor: theme.colorScheme.error,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        final theme = Theme.of(context);
        final localizations = AppLocalizations.of(context)!;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('${localizations.errorOpeningDownload}: ${e.toString()}'),
            backgroundColor: theme.colorScheme.error,
          ),
        );
      }
    }
  }

  String _buildUrl(String path, String language) {
    if (path.startsWith('http://') || path.startsWith('https://')) {
      // If it's a frontend URL, add language
      final frontendHost = AppConfig.frontendUrl
          .replaceAll('http://', '')
          .replaceAll('https://', '');
      if (path.contains(frontendHost) ||
          path.contains('localhost:3000') ||
          path.contains('10.0.2.2:3000') ||
          path.contains('website-databank.fly.dev')) {
        return UrlHelper.buildFrontendUrlWithLanguage(path, language);
      }
      // Backoffice URL, return as is
      return path;
    }
    // Check if it's a backend path (forms routes, admin routes, and API routes are backend)
    if (path.startsWith('/forms/') ||
        path.startsWith('/api/') ||
        path.startsWith('/admin/') ||
        path.startsWith('/login') ||
        path.startsWith('/logout')) {
      return UrlHelper.buildBackendUrl(path);
    }
    // Check if it's a frontend path (starts with /)
    if (path.startsWith('/')) {
      return UrlHelper.buildFrontendUrlWithLanguage(path, language);
    }
    // Backoffice URL
    return UrlHelper.buildBackendUrl(path);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<AuthProvider, LanguageProvider>(
      builder: (context, authProvider, languageProvider, child) {
        final language = languageProvider.currentLanguage;
        final url = _buildUrl(widget.initialUrl, language);
        final user = authProvider.user;
        final isAdmin = user != null &&
            (user.role == 'admin' || user.role == 'system_manager');

        final localizations = AppLocalizations.of(context)!;
        final theme = Theme.of(context);

        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: _pageTitle ?? localizations.loading,
            actions: [
              if (_webViewController != null)
                IconButton(
                  icon: const Icon(Icons.refresh),
                  onPressed: () {
                    _webViewController?.reload();
                  },
                  tooltip: localizations.refresh,
                ),
              IconButton(
                icon: const Icon(Icons.close),
                onPressed: () {
                  Navigator.of(context).pop();
                },
                tooltip: 'Close',
              ),
            ],
          ),
          body: Container(
            color: theme.scaffoldBackgroundColor,
            child: SafeArea(
              top: true,
              bottom: false,
              child: ListView(
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  SizedBox(
                    height: MediaQuery.of(context).size.height -
                        MediaQuery.of(context).padding.top -
                        kToolbarHeight -
                        50 - // Bottom navigation bar height
                        MediaQuery.of(context)
                            .padding
                            .bottom, // Safe area bottom padding
                    child: Stack(
                      children: [
                        InAppWebView(
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
                            //   print('[WEBVIEW] ${consoleMessage.messageLevel}: ${consoleMessage.message}');
                            // }
                          },
                          shouldOverrideUrlLoading:
                              (controller, navigationAction) async {
                            // Validate URL before loading
                            final url = navigationAction.request.url;
                            if (url != null && !WebViewService.isUrlAllowed(url)) {
                              DebugLogger.logWarn(
                                  'WEBVIEW', 'Blocked navigation to: $url');
                              // Show error message
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
                            // Allow navigation for valid URLs
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

                            // Update app bar title
                            final title = await controller.getTitle();
                            if (title != null && mounted) {
                              setState(() {
                                _pageTitle = title;
                              });
                            }
                          },
                          onTitleChanged: (controller, title) {
                            if (title != null && mounted) {
                              setState(() {
                                _pageTitle = title;
                              });
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
                                  '[WEBVIEW] Ignored error: ${error.description}');
                              return;
                            }

                            setState(() {
                              _isLoading = false;
                              _error = error.description;
                            });
                          },
                          onReceivedHttpError: (controller, request, response) {
                            final statusCode = response.statusCode;
                            if (statusCode != null && statusCode >= 400) {
                              setState(() {
                                _isLoading = false;
                                _error = 'HTTP Error $statusCode';
                              });
                            }
                          },
                          onDownloadStart:
                              (InAppWebViewController controller, Uri url) {
                            // Handle file downloads by opening in external browser
                            // The second parameter is a Uri directly
                            _handleDownload(url);
                          },
                        ),
                        // Loading Indicator
                        if (_isLoading && _progress < 1.0)
                          Column(
                            children: [
                              LinearProgressIndicator(
                                value: _progress,
                                backgroundColor: context.dividerColor,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  Color(AppConstants.ifrcRed),
                                ),
                                minHeight: 3,
                              ),
                              Expanded(
                                child: Container(
                                  decoration: BoxDecoration(
                                    gradient: LinearGradient(
                                      begin: Alignment.topCenter,
                                      end: Alignment.bottomCenter,
                                      colors: [
                                        context.navyBackgroundColor(
                                            opacity: 0.05),
                                        theme.scaffoldBackgroundColor,
                                      ],
                                    ),
                                  ),
                                  child: Center(
                                    child: Column(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        CircularProgressIndicator(
                                          valueColor:
                                              AlwaysStoppedAnimation<Color>(
                                            Color(AppConstants.ifrcRed),
                                          ),
                                        ),
                                        const SizedBox(height: 16),
                                        Text(
                                          localizations.loading,
                                          style: const TextStyle(
                                            color: Color(
                                                AppConstants.textSecondary),
                                            fontSize: 14,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        // Error Display
                        if (_error != null && !_isLoading)
                          Container(
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
                                        color:
                                            const Color(AppConstants.errorColor)
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
                                      'Oops! Something went wrong',
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
                                          borderRadius:
                                              BorderRadius.circular(12),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          floatingActionButton: widget.initialUrl.contains('/countries/')
              ? FloatingActionButton(
                  heroTag: 'menu_button_webview',
                  onPressed: () => _showNavigationMenu(context, languageProvider, theme, localizations, language),
                  backgroundColor: Color(AppConstants.ifrcRed),
                  foregroundColor: theme.colorScheme.onPrimary,
                  child: const Icon(Icons.menu),
                  tooltip: 'Navigation Menu',
                )
              : null,
          bottomNavigationBar: AppBottomNavigationBar(
            currentIndex: _currentNavIndex,
            // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
          ),
        );
      },
    );
  }

  void _showNavigationMenu(BuildContext context, LanguageProvider languageProvider, ThemeData theme, AppLocalizations localizations, String language) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAdmin = user != null && (user.role == 'admin' || user.role == 'system_manager');
    final isAuthenticated = authProvider.isAuthenticated;
    final isFocalPoint = user != null && user.role == 'focal_point';

    final resourcesTabIndex = 0;
    final homeTabIndex = 2;
    final disaggregationTabIndex = 3;

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.85,
          ),
          decoration: BoxDecoration(
            color: theme.scaffoldBackgroundColor,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: theme.dividerColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                  child: Text(
                    'Navigation',
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: theme.colorScheme.onSurface,
                    ),
                  ),
                ),
                const Divider(height: 1),
                Flexible(
                  child: ListView(
                    shrinkWrap: true,
                    physics: const ClampingScrollPhysics(),
                    children: [
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.home,
                        title: localizations.home ?? 'Global Overview',
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).popUntil((route) {
                            return route.isFirst || route.settings.name == AppRoutes.dashboard;
                          });
                        },
                      ),
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.library_books,
                        title: localizations.indicatorBank,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          Navigator.of(context).pushNamed(AppRoutes.indicatorBank);
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
                            Navigator.pop(bottomSheetContext);
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
                            Navigator.pop(bottomSheetContext);
                            Navigator.of(context).pop();
                            Navigator.of(context).pushNamed(AppRoutes.resources);
                          },
                        ),
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.public,
                        title: 'Countries',
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          _showCountriesSheet(context, theme);
                        },
                      ),
                      Padding(
                        padding: const EdgeInsets.only(top: 8, left: 24, right: 24, bottom: 8),
                        child: Text(
                          'Analysis',
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface.withOpacity(0.7),
                          ),
                        ),
                      ),
                      // Disaggregation Analysis - navigate to native screen
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.analytics,
                        title: localizations.disaggregationAnalysis,
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          Navigator.of(context).pushNamed(AppRoutes.disaggregationAnalysis);
                        },
                      ),
                      _buildMenuTile(
                        context: context,
                        theme: theme,
                        icon: Icons.bar_chart,
                        title: 'Data Visualization',
                        onTap: () {
                          Navigator.pop(bottomSheetContext);
                          Navigator.of(context).pop();
                          final fullUrl = UrlHelper.buildFrontendUrlWithLanguage('/dataviz', language);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: fullUrl,
                          );
                        },
                      ),
                      const SizedBox(height: 16),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showCountriesSheet(BuildContext context, ThemeData theme) {
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
                Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: theme.dividerColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Countries',
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () => Navigator.pop(bottomSheetContext),
                        tooltip: 'Close',
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
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
  }) {
    return ListTile(
      dense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: Icon(
        icon,
        color: Color(AppConstants.ifrcRed),
        size: 20,
      ),
      title: Text(
        title,
        style: theme.textTheme.bodyLarge?.copyWith(
          fontWeight: FontWeight.w500,
          color: theme.colorScheme.onSurface,
        ),
      ),
      trailing: Icon(
        Icons.chevron_right,
        color: theme.colorScheme.onSurface.withOpacity(0.3),
        size: 20,
      ),
      onTap: onTap,
    );
  }
}
