import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:provider/provider.dart';
import '../../services/session_service.dart';
import '../../services/webview_service.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';

class AzureLoginScreen extends StatefulWidget {
  const AzureLoginScreen({super.key});

  @override
  State<AzureLoginScreen> createState() => _AzureLoginScreenState();
}

class _AzureLoginScreenState extends State<AzureLoginScreen> {
  InAppWebViewController? _webViewController;
  final SessionService _sessionService = SessionService();
  bool _isLoading = true;
  double _progress = 0;
  String? _error;

  String get _azureLoginUrl {
    return '${AppConfig.baseApiUrl}${AppConfig.azureLoginEndpoint}';
  }

  bool _isSuccessUrl(String? url) {
    if (url == null) return false;

    final uri = Uri.tryParse(url);
    if (uri == null) return false;

    final backendHost = Uri.parse(AppConfig.baseApiUrl).host;

    // Must be on the backend domain
    if (uri.host != backendHost && uri.host != '') return false;

    // Success indicators:
    // 1. Dashboard endpoint
    // 2. Azure callback endpoint (processing, will redirect)
    // 3. Any backend URL that's not a login page
    return uri.path == AppConfig.dashboardEndpoint ||
        uri.path == '/dashboard' ||
        uri.path == AppConfig.azureCallbackEndpoint ||
        uri.path == '/auth/azure/callback' ||
        (uri.host == backendHost &&
            !uri.path.contains('/login') &&
            !uri.path.contains('/auth/login'));
  }

  bool _isDashboardUrl(String? url) {
    if (url == null) return false;

    final uri = Uri.tryParse(url);
    if (uri == null) return false;

    final backendHost = Uri.parse(AppConfig.baseApiUrl).host;

    // Check if we're on the dashboard
    return (uri.host == backendHost || uri.host == '') &&
        (uri.path == AppConfig.dashboardEndpoint ||
            uri.path == '/dashboard' ||
            uri.path == '/');
  }

  Future<void> _extractAndSaveSession(String url) async {
    try {
      if (_webViewController == null) return;

      final backendUri = Uri.parse(AppConfig.backendUrl);
      final backendUrl = AppConfig.backendUrl;

      // Get cookies from WebView for the backend domain
      final cookieManager = CookieManager.instance();
      final cookies = await cookieManager.getCookies(
        url: WebUri(backendUrl),
      );

      print('[AZURE LOGIN] Found ${cookies.length} cookies');

      // Find session cookie (Flask session cookie is usually named 'session')
      Cookie? sessionCookie;
      for (var cookie in cookies) {
        final cookieName = cookie.name.toLowerCase();
        print('[AZURE LOGIN] Cookie: $cookieName');
        if (cookieName == 'session') {
          sessionCookie = cookie;
          break;
        }
      }

      if (sessionCookie != null) {
        // Format cookie string for session service (format: "session=value")
        // Remove any existing path or domain attributes for storage
        final cookieString = '${sessionCookie.name}=${sessionCookie.value}';
        await _sessionService.saveSessionCookie(cookieString);
        await _sessionService.injectSessionIntoWebView();

        print('[AZURE LOGIN] Session cookie extracted and saved');

        // Try to refresh user profile through auth provider
        final authProvider = Provider.of<AuthProvider>(context, listen: false);
        await authProvider.refreshUser();
      } else {
        print('[AZURE LOGIN] WARNING: No session cookie found');
        // Wait a bit and try again - cookies might not be set yet
        await Future.delayed(const Duration(milliseconds: 500));
        final retryCookies =
            await cookieManager.getCookies(url: WebUri(backendUrl));
        for (var cookie in retryCookies) {
          if (cookie.name.toLowerCase() == 'session') {
            final cookieString = '${cookie.name}=${cookie.value}';
            await _sessionService.saveSessionCookie(cookieString);
            await _sessionService.injectSessionIntoWebView();
            print('[AZURE LOGIN] Session cookie found on retry');
            final authProvider =
                Provider.of<AuthProvider>(context, listen: false);
            await authProvider.refreshUser();
            break;
          }
        }
      }
    } catch (e) {
      print('[AZURE LOGIN] Error extracting session: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(localizations.loginWithIfrcAccount),
        backgroundColor: theme.appBarTheme.backgroundColor,
        foregroundColor: theme.appBarTheme.foregroundColor,
      ),
      body: Stack(
        children: [
          InAppWebView(
            initialUrlRequest: URLRequest(
              url: WebUri(_azureLoginUrl),
            ),
            initialSettings: InAppWebViewSettings(
              javaScriptEnabled: true,
              domStorageEnabled: true,
              thirdPartyCookiesEnabled: true,
              cacheEnabled: true,
              clearCache: false,
              useHybridComposition: true,
            ),
            onWebViewCreated: (controller) {
              _webViewController = controller;
            },
            onLoadStart: (controller, url) {
              setState(() {
                _isLoading = true;
                // Clear error when starting to load - page might load successfully
                _error = null;
              });

              final urlString = url.toString();
              print('[AZURE LOGIN] Loading: $urlString');

              // If we're on the callback endpoint, wait for redirect
              // If we're on the dashboard, extract cookies and close
              if (_isDashboardUrl(urlString)) {
                print(
                    '[AZURE LOGIN] Dashboard URL detected, extracting session...');
                _extractAndSaveSession(urlString).then((_) {
                  // Give it a moment for cookies to be fully set
                  Future.delayed(const Duration(milliseconds: 800), () {
                    if (mounted) {
                      Navigator.of(context).pop(true); // Return success
                      Navigator.of(context)
                          .pushReplacementNamed(AppRoutes.dashboard);
                    }
                  });
                });
              }
            },
            onLoadStop: (controller, url) async {
              setState(() {
                _isLoading = false;
                // Clear error if page loaded successfully
                _error = null;
              });

              final urlString = url.toString();
              print('[AZURE LOGIN] Loaded: $urlString');

              // Wait for dashboard to load before extracting cookies
              if (_isDashboardUrl(urlString)) {
                print('[AZURE LOGIN] Dashboard loaded, extracting session...');
                await _extractAndSaveSession(urlString);
                // Give it a moment for cookies to be fully set and profile loaded
                Future.delayed(const Duration(milliseconds: 800), () {
                  if (mounted) {
                    Navigator.of(context).pop(true);
                    Navigator.of(context)
                        .pushReplacementNamed(AppRoutes.dashboard);
                  }
                });
              }
            },
            onProgressChanged: (controller, progress) {
              setState(() {
                _progress = progress / 100;
              });
            },
            onReceivedError: (controller, request, error) {
              // Only show errors for main frame navigation failures
              // Ignore sub-resource errors (images, CSS, etc.)
              if (request.isForMainFrame == true) {
                // Check if this is an ignorable error
                if (WebViewService.shouldIgnoreError(error.description)) {
                  print('[AZURE LOGIN] Ignored error: ${error.description}');
                  return;
                }

                print('[AZURE LOGIN] Main frame error: ${error.description}');
                // Don't set error immediately - wait to see if page loads
                // Only show error if page doesn't load successfully
                Future.delayed(const Duration(milliseconds: 1000), () {
                  if (mounted && _isLoading) {
                    // Still loading after delay, show error
                    setState(() {
                      _isLoading = false;
                      _error = error.description ?? 'Failed to load page';
                    });
                  }
                });
              }
            },
            onReceivedHttpError: (controller, request, response) {
              // Only show errors for main frame navigation failures
              // Ignore HTTP errors from sub-resources (images, CSS, etc.)
              if (request.isForMainFrame == true) {
                final statusCode = response.statusCode;
                if (statusCode != null && statusCode >= 400) {
                  print('[AZURE LOGIN] Main frame HTTP error: $statusCode');
                  // Don't set error immediately - wait to see if page loads
                  // Only show error if page doesn't load successfully
                  Future.delayed(const Duration(milliseconds: 1000), () {
                    if (mounted && _isLoading) {
                      // Still loading after delay, show error
                      setState(() {
                        _isLoading = false;
                        _error = 'HTTP Error $statusCode';
                      });
                    }
                  });
                }
              }
            },
            shouldOverrideUrlLoading: (controller, navigationAction) async {
              final url = navigationAction.request.url?.toString();

              if (url == null) return NavigationActionPolicy.ALLOW;

              final uri = Uri.tryParse(url);
              if (uri == null) return NavigationActionPolicy.ALLOW;

              final backendHost = Uri.parse(AppConfig.baseApiUrl).host;

              // Check if we're being redirected back to login (likely an error)
              if ((uri.host == backendHost || uri.host == '') &&
                  uri.path.contains('/login') &&
                  !uri.path.contains('/login/azure')) {
                print(
                    '[AZURE LOGIN] Redirected to login page, likely cancelled or error');
                // Allow navigation but we'll detect this as an error case
                Future.delayed(const Duration(milliseconds: 500), () {
                  if (mounted && uri.queryParameters.containsKey('error')) {
                    // Azure B2C returned an error
                    final error = uri.queryParameters['error'];
                    final errorDesc = uri.queryParameters['error_description'];
                    setState(() {
                      _isLoading = false;
                      _error =
                          errorDesc ?? error ?? 'Login cancelled or failed';
                    });
                  }
                });
              }

              // Allow all navigation
              return NavigationActionPolicy.ALLOW;
            },
          ),
          // Loading indicator
          if (_isLoading && _error == null)
            Container(
              color: theme.scaffoldBackgroundColor.withOpacity(0.8),
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    CircularProgressIndicator(
                      value: _progress > 0 ? _progress : null,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        Color(AppConstants.ifrcRed),
                      ),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      localizations.loading,
                      style: theme.textTheme.bodyMedium,
                    ),
                  ],
                ),
              ),
            ),
          // Error message
          if (_error != null)
            Container(
              color: theme.scaffoldBackgroundColor,
              padding: const EdgeInsets.all(24),
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.error_outline,
                      size: 64,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      _error!,
                      style: theme.textTheme.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    FilledButton(
                      onPressed: () {
                        setState(() {
                          _error = null;
                          _isLoading = true;
                        });
                        _webViewController?.reload();
                      },
                      child: Text(localizations.retry),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
