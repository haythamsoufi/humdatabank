import 'package:flutter/foundation.dart' show kDebugMode, kReleaseMode;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../services/error_handler.dart';
import '../../services/auth_error_handler.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../config/app_config.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/offline_indicator.dart';
import '../../l10n/app_localizations.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _rememberMe = false;
  bool _obscurePassword = true;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _loadSavedEmail();
  }

  Future<void> _loadSavedEmail() async {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final savedEmail = await authProvider.getSavedEmail();
    if (savedEmail != null) {
      setState(() {
        _emailController.text = savedEmail;
        _rememberMe = true;
      });
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  /// Debug/profile: show server exception text on-screen. Release: friendly copy.
  String _loginFailureMessage(String? rawError, AppLocalizations localizations) {
    if (rawError == null || rawError.isEmpty) {
      return localizations.loginFailed;
    }
    if (!kReleaseMode) {
      return rawError;
    }
    return AuthErrorHandler().getUserFriendlyErrorMessage(rawError);
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isLoading = true;
    });

    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final localizations = AppLocalizations.of(context)!;
    final success = await authProvider.login(
      email: _emailController.text.trim(),
      password: _passwordController.text,
      rememberMe: _rememberMe,
    );

    setState(() {
      _isLoading = false;
    });

    if (success && mounted) {
      Navigator.of(context).pushReplacementNamed(AppRoutes.dashboard);
    } else if (mounted) {
      final errorMessage =
          _loginFailureMessage(authProvider.error, localizations);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(errorMessage),
          backgroundColor: const Color(AppConstants.errorColor),
          duration: Duration(
              seconds: !kReleaseMode && errorMessage.length > 100 ? 12 : 4),
        ),
      );
    }
  }

  Future<void> _handleQuickLogin(String email, String password) async {
    setState(() {
      _emailController.text = email;
      _passwordController.text = password;
      _rememberMe = true;
      _isLoading = true;
    });

    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final success = await authProvider.quickLogin(email, password);

    setState(() {
      _isLoading = false;
    });

    if (success && mounted) {
      Navigator.of(context).pushReplacementNamed(AppRoutes.dashboard);
    } else if (mounted) {
      final localizations = AppLocalizations.of(context)!;
      final errorMessage =
          _loginFailureMessage(authProvider.error, localizations);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(errorMessage),
          backgroundColor: const Color(AppConstants.errorColor),
          duration: Duration(
              seconds: !kReleaseMode && errorMessage.length > 100 ? 12 : 4),
        ),
      );
    }
  }

  Future<void> _handleAzureLogin() async {
    try {
      // Navigate to Azure login screen with WebView
      // The AzureLoginScreen will handle navigation to dashboard on success
      await Navigator.of(context).pushNamed(
        AppRoutes.azureLogin,
      );
    } catch (e, stackTrace) {
      if (mounted) {
        final errorHandler = ErrorHandler();
        final error = errorHandler.parseError(
          error: e,
          stackTrace: stackTrace,
          context: 'Azure Login',
        );
        errorHandler.logError(error);

        final localizations = AppLocalizations.of(context)!;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
                '${localizations.couldNotOpenAzureLogin}: ${error.getUserMessage()}'),
            backgroundColor: const Color(AppConstants.errorColor),
            duration: const Duration(seconds: 5),
          ),
        );
      }
    }
  }

  /// Route `arguments` may be an int **page** tab index (main shell PageView).
  int _bottomNavHighlightIndex(BuildContext context) {
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is int && args >= -1 && args < 32) {
      return args;
    }
    return AppBottomNavigationBar.noTabSelected;
  }

  @override
  Widget build(BuildContext context) {
    const loginEnabled = AppConfig.loginEnabled;
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: Stack(
          fit: StackFit.expand,
          clipBehavior: Clip.none,
          children: [
            Positioned.fill(
              child: SingleChildScrollView(
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal:
                        MediaQuery.of(context).size.width > 600 ? 40 : 20,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      const SizedBox(height: 20),
                // Logo - Instagram style
                Image.asset(
                  'assets/images/ifrc_logo.png',
                  height: 80,
                  errorBuilder: (context, error, stackTrace) {
                    return Container(
                      height: 80,
                      width: 80,
                      decoration: BoxDecoration(
                        color: context.lightSurfaceColor,
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: context.borderColor,
                          width: 1,
                        ),
                      ),
                      child: Icon(
                        Icons.account_circle,
                        size: 50,
                        color: context.textSecondaryColor,
                      ),
                    );
                  },
                ),
                const SizedBox(height: 40),
                // Login Card - Instagram style
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal:
                        MediaQuery.of(context).size.width > 600 ? 40 : 20,
                    vertical: 32,
                  ),
                  decoration: BoxDecoration(
                    color: Theme.of(context).cardTheme.color ??
                        Theme.of(context).colorScheme.surface,
                    border: Border.all(
                      color: context.borderColor,
                      width: 1,
                    ),
                    borderRadius: BorderRadius.circular(1),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        localizations.appName,
                        style: Theme.of(context)
                            .textTheme
                            .displaySmall
                            ?.copyWith(
                              fontWeight: FontWeight.w400,
                              fontSize: MediaQuery.of(context).size.width > 600
                                  ? 28
                                  : 24,
                              letterSpacing: 0,
                            ),
                        textAlign: TextAlign.center,
                        overflow: TextOverflow.ellipsis,
                        maxLines: 2,
                      ),
                      const SizedBox(height: 24),
                      ..._buildLoginSection(
                          loginEnabled, context, localizations),
                    ],
                  ),
                ),
                // Quick login: debug + local backoffice only (not release/remote CI)
                if (AppConfig.isQuickLoginEnabled) ...[
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Theme.of(context).cardTheme.color ??
                          Theme.of(context).colorScheme.surface,
                      border: Border.all(
                        color: context.borderColor,
                        width: 1,
                      ),
                      borderRadius: BorderRadius.circular(1),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.science,
                              size: 14,
                              color: context.textSecondaryColor,
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                localizations.quickLoginTesting,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(
                                      color: context.textSecondaryColor,
                                      fontWeight: FontWeight.w400,
                                    ),
                                textAlign: TextAlign.center,
                                overflow: TextOverflow.ellipsis,
                                maxLines: 2,
                              ),
                            ),
                          ],
                        ),
                        if (kDebugMode) ...[
                          const SizedBox(height: 8),
                          SelectableText(
                            AppConfig.backendUrl,
                            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                  fontFamily: 'monospace',
                                  color: context.textSecondaryColor,
                                ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                        const SizedBox(height: 16),
                        FilledButton(
                          onPressed: _isLoading
                              ? null
                              : () => _handleQuickLogin(
                                    'test_admin@ifrc.org',
                                    'test123',
                                  ),
                          style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                            minimumSize: const Size(double.infinity, 50),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                            elevation: 0,
                          ),
                          child: Text(
                            localizations.testAsAdmin,
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                            style: TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w600,
                              color: Theme.of(context).colorScheme.onPrimary,
                              letterSpacing: -0.41,
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        FilledButton(
                          onPressed: _isLoading
                              ? null
                              : () => _handleQuickLogin(
                                    'test_focal@ifrc.org',
                                    'test123',
                                  ),
                          style: FilledButton.styleFrom(
                            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                            minimumSize: const Size(double.infinity, 50),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(10),
                            ),
                            elevation: 0,
                          ),
                          child: Text(
                            localizations.testAsFocalPoint,
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                            style: TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w600,
                              color: Theme.of(context).colorScheme.onPrimary,
                              letterSpacing: -0.41,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
                const SizedBox(height: 80),
              ],
            ),
          ),
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
),
      bottomNavigationBar: Consumer<AuthProvider>(
        builder: (context, auth, _) {
          final chatbot = auth.user?.chatbotEnabled ?? false;
          return AppBottomNavigationBar(
            currentIndex: _bottomNavHighlightIndex(context),
            chatbotEnabled: chatbot,
            onTap: (index) {
              Navigator.of(context).pushReplacementNamed(AppRoutes.dashboard);
            },
          );
        },
      ),
    );
  }

  List<Widget> _buildLoginSection(
      bool loginEnabled, BuildContext context, AppLocalizations localizations) {
    if (!loginEnabled) {
      return [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: context.isDarkTheme
                ? Colors.blue.shade900.withValues(alpha: 0.45)
                : Colors.blue.shade50,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: context.isDarkTheme
                  ? Colors.blue.shade600.withValues(alpha: 0.85)
                  : Colors.blue.shade200,
              width: 1.5,
            ),
          ),
          child: Column(
            children: [
              Icon(
                Icons.lock_clock_rounded,
                size: 48,
                color: context.isDarkTheme
                    ? Colors.blue.shade200
                    : Colors.blue.shade700,
              ),
              const SizedBox(height: 16),
              Text(
                localizations.publicLoginDisabled,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: context.isDarkTheme
                          ? Colors.blue.shade100
                          : Colors.blue.shade900,
                    ),
                textAlign: TextAlign.center,
                overflow: TextOverflow.visible,
                maxLines: 3,
              ),
              const SizedBox(height: 8),
              Text(
                localizations.testerAccountsInfo,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: context.isDarkTheme
                          ? Colors.blue.shade200
                          : Colors.blue.shade700,
                    ),
                textAlign: TextAlign.center,
                overflow: TextOverflow.visible,
                maxLines: 3,
              ),
            ],
          ),
        ),
      ];
    }

    // IFRC-hosted backoffice or unknown remote: SSO only (no email/password form)
    if (AppConfig.isIfrcBackendHost ||
        !AppConfig.isManualCredentialLoginEnabled) {
      return [
        FilledButton(
          onPressed: _isLoading ? null : _handleAzureLogin,
          style: FilledButton.styleFrom(
            backgroundColor: Color(AppConstants.ifrcRed),
            foregroundColor: Theme.of(context).colorScheme.onSecondary,
            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
            minimumSize: const Size(double.infinity, 50),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
            ),
            elevation: 0,
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Image.asset(
                'assets/images/ifrc_logo.png',
                height: 20,
                width: 20,
                errorBuilder: (context, error, stackTrace) {
                  return Icon(
                    Icons.account_circle,
                    size: 20,
                    color: Theme.of(context).colorScheme.onSecondary,
                  );
                },
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  localizations.yourAccountOrCreateAccount,
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                  style: TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    color: Theme.of(context).colorScheme.onSecondary,
                    letterSpacing: -0.41,
                  ),
                ),
              ),
            ],
          ),
        ),
      ];
    }

    return [
      Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Azure Login Button (IFRC Account)
            FilledButton(
              onPressed: _isLoading ? null : _handleAzureLogin,
              style: FilledButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
                foregroundColor: Theme.of(context).colorScheme.onSecondary,
                padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                minimumSize: const Size(double.infinity, 50),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                elevation: 0,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Image.asset(
                    'assets/images/ifrc_logo.png',
                    height: 20,
                    width: 20,
                    errorBuilder: (context, error, stackTrace) {
                      return Icon(
                        Icons.account_circle,
                        size: 20,
                        color: Theme.of(context).colorScheme.onSecondary,
                      );
                    },
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      localizations.yourAccountOrCreateAccount,
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1,
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                        color: Theme.of(context).colorScheme.onSecondary,
                        letterSpacing: -0.41,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            // Email Field - Instagram style
            Semantics(
              label: localizations.phoneUsernameEmail,
              textField: true,
              child: TextFormField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                style: TextStyle(
                  fontSize: 14,
                  color: Theme.of(context).colorScheme.onSurface,
                ),
                decoration: InputDecoration(
                  labelText: localizations.phoneUsernameEmail,
                  labelStyle: TextStyle(
                    fontSize: 12,
                    color: context.textSecondaryColor,
                  ),
                  filled: true,
                  fillColor: context.lightSurfaceColor,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(4),
                    borderSide: BorderSide(color: context.borderColor),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(4),
                    borderSide: BorderSide(color: context.borderColor),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(4),
                    borderSide: BorderSide(
                      color: context.isDarkTheme
                          ? Colors.white.withValues(alpha: 0.7)
                          : Theme.of(context).colorScheme.primary,
                      width: 1.5,
                    ),
                  ),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return localizations.pleaseEnterEmail;
                  }
                  if (!value.contains('@')) {
                    return localizations.pleaseEnterValidEmail;
                  }
                  return null;
                },
              ),
            ),
            const SizedBox(height: 12),
            // Password Field - Instagram style
            Semantics(
              label: localizations.password,
              textField: true,
              child: TextFormField(
                controller: _passwordController,
                obscureText: _obscurePassword,
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => _handleLogin(),
                style: TextStyle(
                  fontSize: 14,
                  color: Theme.of(context).colorScheme.onSurface,
                ),
                decoration: InputDecoration(
                  labelText: localizations.password,
                  labelStyle: TextStyle(
                    fontSize: 12,
                    color: context.textSecondaryColor,
                  ),
                  filled: true,
                  fillColor: context.lightSurfaceColor,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  suffixIcon: Semantics(
                    label: _obscurePassword
                        ? localizations.show
                        : localizations.hide,
                    button: true,
                    child: TextButton(
                      onPressed: () {
                        setState(() {
                          _obscurePassword = !_obscurePassword;
                        });
                      },
                      child: Text(
                        _obscurePassword ? localizations.show : localizations.hide,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: Theme.of(context).colorScheme.onSurface,
                        ),
                      ),
                    ),
                  ),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(4),
                    borderSide: BorderSide(color: context.borderColor),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(4),
                    borderSide: BorderSide(color: context.borderColor),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(4),
                    borderSide: BorderSide(
                      color: context.isDarkTheme
                          ? Colors.white.withValues(alpha: 0.7)
                          : Theme.of(context).colorScheme.primary,
                      width: 1.5,
                    ),
                  ),
                ),
                validator: (value) {
                  if (value == null || value.isEmpty) {
                    return localizations.pleaseEnterPassword;
                  }
                  return null;
                },
              ),
            ),
            const SizedBox(height: 16),
            // Forgot Password
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () {
                  final t = Theme.of(context);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(
                        localizations.forgotPasswordComingSoon,
                        style: TextStyle(color: t.colorScheme.onInverseSurface),
                      ),
                      backgroundColor: t.colorScheme.inverseSurface,
                    ),
                  );
                },
                style: TextButton.styleFrom(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
                child: Text(
                  localizations.forgotPassword,
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w400,
                    color: context.linkOnSurfaceColor,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            // Login Button - iOS style
            Semantics(
              label: localizations.logIn,
              button: true,
              enabled: !_isLoading,
              child: FilledButton(
                onPressed: _isLoading ? null : _handleLogin,
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
                  minimumSize: const Size(double.infinity, 50),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                  elevation: 0,
                ),
              child: _isLoading
                  ? SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          Theme.of(context).colorScheme.onPrimary,
                        ),
                      ),
                    )
                  : Text(
                      localizations.logIn,
                      style: TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                        color: Theme.of(context).colorScheme.onPrimary,
                        letterSpacing: -0.41,
                      ),
                    ),
              ),
            ),
            const SizedBox(height: 24),
            // Divider
            Row(
              children: [
                Expanded(
                  child: Container(
                    height: 0.5,
                    color: context.borderColor,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    localizations.or,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: context.textSecondaryColor,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
                Expanded(
                  child: Container(
                    height: 0.5,
                    color: context.borderColor,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 24),
            // Register Link
            Wrap(
              alignment: WrapAlignment.center,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  localizations.dontHaveAccount,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: context.textSecondaryColor,
                      ),
                ),
                const SizedBox(width: 4),
                TextButton(
                  onPressed: () {
                    final t = Theme.of(context);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          localizations.registrationComingSoon,
                          style: TextStyle(color: t.colorScheme.onInverseSurface),
                        ),
                        backgroundColor: t.colorScheme.inverseSurface,
                      ),
                    );
                  },
                  style: TextButton.styleFrom(
                    padding: EdgeInsets.zero,
                    minimumSize: Size.zero,
                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  ),
                  child: Text(
                    localizations.signUp,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: context.linkOnSurfaceColor,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    ];
  }
}
