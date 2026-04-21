import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/deep_link_service.dart';
import '../../services/jwt_token_service.dart';
import '../../services/session_service.dart';
import '../../services/auth_service.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/debug_logger.dart';

/// Handles IFRC/Azure B2C login via Chrome Custom Tabs.
///
/// Chrome Custom Tabs use the system Chrome browser engine, which avoids the
/// `X-Requested-With: <packageName>` header that Android's embedded WebView
/// (InAppWebView) adds to every request — that header causes Azure AD B2C to
/// return HTTP 403 for embedded-browser OAuth flows.
///
/// Flow:
///   1. This screen launches `/login/azure?mobile_return_scheme=humdatabank`
///      in a Chrome Custom Tab.
///   2. The backend embeds `mobile: true` in the signed OAuth state JWT.
///   3. After successful Azure B2C login the backend issues JWT tokens and
///      redirects to `humdatabank://oauth-success?access_token=...&refresh_token=...`.
///   4. Android delivers that URI to the app as a deep link.
///   5. [DeepLinkService] broadcasts it on [DeepLinkService.oauthTokenStream].
///   6. This screen receives the tokens, saves them, and navigates to the dashboard.
class AzureLoginScreen extends StatefulWidget {
  const AzureLoginScreen({super.key});

  @override
  State<AzureLoginScreen> createState() => _AzureLoginScreenState();
}

class _AzureLoginScreenState extends State<AzureLoginScreen>
    with WidgetsBindingObserver {
  final JwtTokenService _jwtService = JwtTokenService();
  final SessionService _sessionService = SessionService();

  bool _waiting = true;
  bool _launched = false;
  String? _error;

  StreamSubscription<Map<String, String>>? _oauthSub;
  Timer? _timeoutTimer;

  /// The URL sent to Chrome Custom Tab — includes the mobile deep-link flag.
  String get _azureLoginUrl =>
      '${AppConfig.baseApiUrl}${AppConfig.azureLoginEndpoint}'
      '?mobile_return_scheme=humdatabank';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Tell AuthService not to clear auth state while the browser flow is open.
    // The app receives AppLifecycleState.resumed when the CCT closes, and
    // refreshSession() would otherwise wipe the state before the deep-link
    // tokens are delivered by app_links and saved here.
    AuthService.oauthFlowPending = true;

    _oauthSub = DeepLinkService.oauthTokenStream.listen(_handleOAuthDeepLink);

    // Consume any OAuth token that arrived via the initial deep link before
    // this screen existed (cold-start race: the app was killed, the browser
    // redirect re-launched it, and getInitialLink() fired before we subscribed).
    final pending = DeepLinkService.consumePendingOAuthTokens();
    if (pending != null) {
      DebugLogger.logInfo('AZURE LOGIN',
          'Consuming cold-start OAuth tokens — '
          'skipping Chrome Custom Tab launch. '
          'Keys: ${pending.keys.join(", ")}');
      _handleOAuthDeepLink(pending);
      return; // _launchOAuth is skipped — tokens already in hand
    }

    DebugLogger.logInfo('AZURE LOGIN',
        'No pending cold-start tokens — launching B2C in Chrome Custom Tab');
    _launchOAuth();
  }

  @override
  void dispose() {
    // Clear the OAuth guard so normal session refresh resumes.
    AuthService.oauthFlowPending = false;
    WidgetsBinding.instance.removeObserver(this);
    _oauthSub?.cancel();
    _timeoutTimer?.cancel();
    super.dispose();
  }

  Future<void> _launchOAuth() async {
    setState(() {
      _waiting = true;
      _launched = false;
      _error = null;
    });

    // Cancel any previous timeout.
    _timeoutTimer?.cancel();
    _timeoutTimer = Timer(const Duration(minutes: 5), () {
      if (mounted && _waiting) {
        setState(() {
          _waiting = false;
          _error = 'Sign-in timed out. Please try again.';
        });
      }
    });

    try {
      final uri = Uri.parse(_azureLoginUrl);
      DebugLogger.logInfo('AZURE LOGIN', 'Launching Chrome Custom Tab: $uri');

      // LaunchMode.inAppBrowserView → Chrome Custom Tab on Android.
      final launched = await launchUrl(
        uri,
        mode: LaunchMode.inAppBrowserView,
      );

      if (!launched && mounted) {
        DebugLogger.logWarn('AZURE LOGIN', 'launchUrl returned false');
        setState(() {
          _waiting = false;
          _error = 'Could not open the sign-in browser. Please try again.';
        });
      } else {
        setState(() => _launched = true);
        DebugLogger.logInfo('AZURE LOGIN', 'Chrome Custom Tab launched');
      }
    } catch (e) {
      DebugLogger.logError('AZURE LOGIN launch error: $e');
      if (mounted) {
        setState(() {
          _waiting = false;
          _error = AppLocalizations.of(context)!.couldNotOpenAzureLogin;
        });
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // When the user returns to the app from the browser, the deep link should
    // arrive via the stream shortly. Log the resume so it appears in debug output.
    if (state == AppLifecycleState.resumed && _launched && _waiting) {
      DebugLogger.logInfo('AZURE LOGIN', 'App resumed — awaiting OAuth deep link');
    }
  }

  /// Called when the OAuth deep link `humdatabank://oauth-success?...` arrives.
  Future<void> _handleOAuthDeepLink(Map<String, String> params) async {
    _timeoutTimer?.cancel();

    final accessToken = params['access_token'];
    final refreshToken = params['refresh_token'];
    final expiresInStr = params['expires_in'];
    final expiresIn = int.tryParse(expiresInStr ?? '') ?? 1800;

    DebugLogger.logInfo('AZURE LOGIN',
        'OAuth deep link received — '
        'access_token present: ${accessToken != null}, '
        'refresh_token present: ${refreshToken != null}, '
        'expires_in: ${expiresIn}s');

    if (accessToken == null || accessToken.isEmpty ||
        refreshToken == null || refreshToken.isEmpty) {
      DebugLogger.logWarn('AZURE LOGIN',
          'Deep link missing tokens — '
          'access_token empty: ${accessToken == null || accessToken.isEmpty}, '
          'refresh_token empty: ${refreshToken == null || refreshToken.isEmpty}');
      if (mounted) {
        setState(() {
          _waiting = false;
          _error = 'Sign-in failed: missing tokens. Please try again.';
        });
      }
      return;
    }

    // Dismiss the in-app browser (Chrome Custom Tab / SFSafariViewController)
    // before navigating away. This is a no-op if already dismissed by the OS.
    try {
      await closeInAppWebView();
    } catch (_) {}

    try {
      // Persist JWT tokens so all API calls use Bearer auth.
      //
      // IMPORTANT: do NOT set oauthFlowPending = false before this await.
      // The guard must stay True until tokens are durably on disk.  Clearing
      // it earlier opens a race where a concurrent refreshSession() (triggered
      // by the AppLifecycleState.resumed event that fires when the CCT closes)
      // sees no refresh token and schedules clearTokens(), which then executes
      // after this save — wiping the just-persisted tokens.
      await _jwtService.saveTokens(
        accessToken: accessToken,
        refreshToken: refreshToken,
        expiresIn: expiresIn,
      );
      // Keep session timestamps in sync for pre-request expiry guard.
      await _sessionService.updateLastValidation();

      // Tokens are safely on disk — release the guard now.  Any refreshSession()
      // that runs from this point forward will find a valid refresh token.
      AuthService.oauthFlowPending = false;

      DebugLogger.logInfo('AZURE LOGIN',
          'JWT tokens saved (expires_in: ${expiresIn}s) — '
          'attempting user profile refresh');

      if (!mounted) return;
      final authProvider = Provider.of<AuthProvider>(context, listen: false);
      await authProvider.refreshUser();

      if (!mounted) return;

      final hasJwt = await _jwtService.hasTokens();
      final jwtExpired = await _jwtService.isAccessTokenExpired();
      if (!mounted) return;
      DebugLogger.logInfo('AZURE LOGIN',
          'Post-refresh state: '
          'isAuthenticated=${authProvider.isAuthenticated}, '
          'user=${authProvider.user?.email ?? "null"}, '
          'hasJwt=$hasJwt, jwtExpired=$jwtExpired');

      if (authProvider.isAuthenticated && authProvider.user != null) {
        DebugLogger.logInfo('AZURE LOGIN',
            'Auth confirmed — navigating to dashboard '
            '(user: ${authProvider.user!.email})');
        Navigator.of(context).pushNamedAndRemoveUntil(
          AppRoutes.dashboard,
          (route) => false,
          arguments: 2,
        );
      } else if (hasJwt && !jwtExpired) {
        // JWT is valid but profile couldn't load (e.g. device offline).
        // Navigate to dashboard — the profile will load when connectivity returns.
        DebugLogger.logWarn('AZURE LOGIN',
            'JWT is valid but user profile not loaded '
            '(likely offline). Navigating to dashboard — '
            'profile will sync when online.');
        Navigator.of(context).pushNamedAndRemoveUntil(
          AppRoutes.dashboard,
          (route) => false,
          arguments: 2,
        );
      } else {
        DebugLogger.logWarn('AZURE LOGIN',
            'Tokens invalid or expired after save '
            '(hasJwt: $hasJwt, jwtExpired: $jwtExpired). '
            'Launching B2C login.');
        _launchOAuth();
      }
    } catch (e) {
      // Always release the guard on failure so normal session refresh resumes.
      AuthService.oauthFlowPending = false;
      DebugLogger.logError('AZURE LOGIN token save error: $e');
      if (mounted) {
        setState(() {
          _waiting = false;
          _error = AppLocalizations.of(context)!.loginFailed;
        });
      }
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
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: _error != null
            ? _buildErrorView(theme, localizations)
            : _buildWaitingView(theme, localizations),
        ),
      ),
    );
  }

  Widget _buildWaitingView(ThemeData theme, AppLocalizations localizations) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(
            Color(AppConstants.ifrcRed),
          ),
        ),
        const SizedBox(height: 28),
        Text(
          _launched
              ? localizations.azureCompleteSignInBrowser
              : localizations.azureOpeningSignInBrowser,
          style: theme.textTheme.bodyLarge,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 32),
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: Text(localizations.cancel),
        ),
        if (_launched) ...[
          const SizedBox(height: 8),
          TextButton(
            onPressed: _launchOAuth,
            child: Text(localizations.azureReopenBrowser),
          ),
        ],
      ],
    );
  }

  Widget _buildErrorView(ThemeData theme, AppLocalizations localizations) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(Icons.error_outline, size: 64, color: theme.colorScheme.error),
        const SizedBox(height: 16),
        Text(
          _error!,
          style: theme.textTheme.bodyLarge,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: () {
            _oauthSub?.cancel();
            _oauthSub = DeepLinkService.oauthTokenStream
                .listen(_handleOAuthDeepLink);
            _launchOAuth();
          },
          child: Text(localizations.retry),
        ),
        const SizedBox(height: 8),
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: Text(localizations.cancel),
        ),
      ],
    );
  }
}
