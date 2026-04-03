import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../providers/shared/auth_provider.dart';
import '../../services/error_handler.dart';
import '../../services/auth_error_handler.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../config/app_config.dart';
import '../../widgets/bottom_navigation_bar.dart';
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
      final errorHandler = AuthErrorHandler();
      final errorMessage = authProvider.error != null
          ? errorHandler.getUserFriendlyErrorMessage(authProvider.error!)
          : localizations.loginFailed;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(errorMessage),
          backgroundColor: const Color(AppConstants.errorColor),
          duration: const Duration(seconds: 4),
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
      final errorHandler = AuthErrorHandler();
      final errorMessage = authProvider.error != null
          ? errorHandler.getUserFriendlyErrorMessage(authProvider.error!)
          : localizations.loginFailed;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(errorMessage),
          backgroundColor: const Color(AppConstants.errorColor),
          duration: const Duration(seconds: 4),
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

  @override
  Widget build(BuildContext context) {
    const loginEnabled = AppConfig.loginEnabled;
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      body: SafeArea(
        child: SingleChildScrollView(
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: MediaQuery.of(context).size.width > 600 ? 40 : 20,
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
                        color: const Color(0xFFFAFAFA),
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: const Color(0xFFDBDBDB),
                          width: 1,
                        ),
                      ),
                      child: const Icon(
                        Icons.account_circle,
                        size: 50,
                        color: Color(0xFF8E8E8E),
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
                // Quick Login Section - Development builds only
                if (AppConfig.isDevelopment) ...[
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
                              color: const Color(0xFF8E8E8E),
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                localizations.quickLoginTesting,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(
                                      color: const Color(0xFF8E8E8E),
                                      fontWeight: FontWeight.w400,
                                    ),
                                textAlign: TextAlign.center,
                                overflow: TextOverflow.ellipsis,
                                maxLines: 2,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        FilledButton(
                          onPressed: _isLoading
                              ? null
                              : () => _handleQuickLogin(
                                    'test_admin@ngo.org',
                                    'test123',
                                  ),
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF0095F6),
                            foregroundColor: Colors.white,
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
                            style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w600,
                              color: Colors.white,
                              letterSpacing: -0.41,
                            ),
                          ),
                        ),
                        const SizedBox(height: 8),
                        FilledButton(
                          onPressed: _isLoading
                              ? null
                              : () => _handleQuickLogin(
                                    'test_focal@ngo.org',
                                    'test123',
                                  ),
                          style: FilledButton.styleFrom(
                            backgroundColor: const Color(0xFF0095F6),
                            foregroundColor: Colors.white,
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
                            style: const TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w600,
                              color: Colors.white,
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
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: -1, // No tab selected on login screen
        onTap: (index) {
          // Navigate to main navigation screen when a tab is tapped
          Navigator.of(context).pushReplacementNamed(AppRoutes.dashboard);
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
            color: Colors.blue.shade50,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: Colors.blue.shade200,
              width: 1.5,
            ),
          ),
          child: Column(
            children: [
              Icon(
                Icons.lock_clock_rounded,
                size: 48,
                color: Colors.blue.shade700,
              ),
              const SizedBox(height: 16),
              Text(
                localizations.publicLoginDisabled,
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: Colors.blue.shade900,
                    ),
                textAlign: TextAlign.center,
                overflow: TextOverflow.visible,
                maxLines: 3,
              ),
              const SizedBox(height: 8),
              Text(
                localizations.testerAccountsInfo,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: Colors.blue.shade700,
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

    // In staging, only show Azure login button
    if (AppConfig.isStaging) {
      return [
        FilledButton(
          onPressed: _isLoading ? null : _handleAzureLogin,
          style: FilledButton.styleFrom(
            backgroundColor: Color(AppConstants.ifrcRed),
            foregroundColor: Colors.white,
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
                  return const Icon(
                    Icons.account_circle,
                    size: 20,
                    color: Colors.white,
                  );
                },
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  localizations.yourAccountOrCreateAccount,
                  overflow: TextOverflow.ellipsis,
                  maxLines: 1,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
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
                foregroundColor: Colors.white,
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
                      return const Icon(
                        Icons.account_circle,
                        size: 20,
                        color: Colors.white,
                      );
                    },
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      localizations.yourAccountOrCreateAccount,
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1,
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
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
                      color: Theme.of(context).colorScheme.primary,
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
                      color: Theme.of(context).colorScheme.primary,
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
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(localizations.forgotPasswordComingSoon),
                      backgroundColor: const Color(0xFF262626),
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
                    color: Color(0xFF0095F6),
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
                  backgroundColor: const Color(0xFF0095F6),
                  foregroundColor: Colors.white,
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
                      style: const TextStyle(
                        fontSize: 17,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
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
                    color: const Color(0xFFDBDBDB),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    localizations.or,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: const Color(0xFF8E8E8E),
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
                Expanded(
                  child: Container(
                    height: 0.5,
                    color: const Color(0xFFDBDBDB),
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
                        color: const Color(0xFF8E8E8E),
                      ),
                ),
                const SizedBox(width: 4),
                TextButton(
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(localizations.registrationComingSoon),
                        backgroundColor: const Color(0xFF262626),
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
                    style: const TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: Color(0xFF0095F6),
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
