import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../services/performance_service.dart';
import '../../utils/debug_logger.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _logoScaleAnimation;
  late Animation<double> _logoFadeAnimation;
  late Animation<double> _titleFadeAnimation;
  late Animation<double> _descriptionFadeAnimation;
  late Animation<double> _loaderFadeAnimation;
  late Animation<double> _attributionFadeAnimation;

  @override
  void initState() {
    super.initState();
    _setupAnimations();
    _checkAuthAndNavigate();
  }

  void _setupAnimations() {
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );

    // Logo scale animation (bounce-in effect)
    _logoScaleAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: Curves.elasticOut,
      ),
    );

    // Logo fade animation
    _logoFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: const Interval(0.0, 0.6, curve: Curves.easeIn),
      ),
    );

    // Title fade and slide animation
    _titleFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: const Interval(0.3, 0.8, curve: Curves.easeOut),
      ),
    );

    // Description fade animation
    _descriptionFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: const Interval(0.5, 1.0, curve: Curves.easeOut),
      ),
    );

    // Loader fade animation
    _loaderFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: const Interval(0.7, 1.0, curve: Curves.easeIn),
      ),
    );

    // Attribution fade animation
    _attributionFadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _animationController,
        curve: const Interval(0.8, 1.0, curve: Curves.easeIn),
      ),
    );

    _animationController.forward();
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _checkAuthAndNavigate() async {
    final performanceService = PerformanceService();
    performanceService.startInit('splash_auth_check');

    // Start loading immediately - splash screen serves as loading screen
    final authProvider = Provider.of<AuthProvider>(context, listen: false);

    // Minimum splash duration (2.5 seconds)
    const minSplashDuration = Duration(milliseconds: 2500);

    // Maximum time to wait for auth check (5 seconds)
    // If backend is not responding, we'll proceed anyway
    const authCheckTimeout = Duration(seconds: 5);

    // Start auth check in background (don't block navigation)
    final authCheckFuture = performanceService.trackOperation(
      'splash_auth_check',
      () async {
        try {
          return await authProvider.checkAuthStatus(forceRevalidate: true)
            .timeout(authCheckTimeout);
        } on TimeoutException {
          // Log timeout but don't throw - allow app to continue
          DebugLogger.logWarn(
            'SPLASH',
            'Auth check timed out after ${authCheckTimeout.inSeconds}s - proceeding with cached auth state'
          );
          return false; // Return false on timeout
        } catch (e) {
          // Log error but don't throw - allow app to continue
          DebugLogger.logWarn(
            'SPLASH',
            'Auth check failed: $e - proceeding with cached auth state'
          );
          return false; // Return false on error
        }
      },
    );

    // Wait for minimum splash duration
    await Future.delayed(minSplashDuration);

    // If auth check completes quickly, wait for it (but don't wait longer than remaining timeout)
    // Calculate remaining timeout (ensure it's not negative)
    final remainingTimeout = authCheckTimeout - minSplashDuration;
    if (remainingTimeout > Duration.zero) {
      try {
        await authCheckFuture.timeout(
          remainingTimeout,
          onTimeout: () {
            // Auth check is taking too long - proceed anyway
            DebugLogger.logInfo(
              'SPLASH',
              'Proceeding to main screen - auth check continues in background'
            );
            return false; // Return false to indicate timeout occurred
          },
        );
      } catch (e) {
        // Auth check failed or timed out - proceed anyway
        DebugLogger.logInfo(
          'SPLASH',
          'Proceeding to main screen despite auth check issue: $e'
        );
      }
    } else {
      // Minimum splash duration already exceeded timeout - proceed immediately
      DebugLogger.logInfo(
        'SPLASH',
        'Minimum splash duration exceeded - proceeding to main screen'
      );
    }

    performanceService.endInit('splash_auth_check');

    if (!mounted) return;

    // Always go to main navigation (Home screen at index 2) - it handles both authenticated and non-authenticated users
    // Auth check can continue in background if it hasn't completed yet
    Navigator.of(context).pushReplacementNamed(
      AppRoutes.dashboard,
      arguments: 2, // Navigate to Home screen (index 2)
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color(AppConstants.ifrcNavy),
              Color(AppConstants.ifrcRed),
            ],
          ),
        ),
        child: Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24.0),
            child: AnimatedBuilder(
              animation: _animationController,
              builder: (context, child) {
                return Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // App logo with scale and fade animation
                    FadeTransition(
                      opacity: _logoFadeAnimation,
                      child: ScaleTransition(
                        scale: _logoScaleAnimation,
                        child: Image.asset(
                          'assets/images/app_icon.png',
                          width: 120,
                          height: 120,
                          fit: BoxFit.contain,
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    // Welcome Text with fade animation
                    FadeTransition(
                      opacity: _titleFadeAnimation,
                      child: SlideTransition(
                        position: Tween<Offset>(
                          begin: const Offset(0, 0.3),
                          end: Offset.zero,
                        ).animate(
                          CurvedAnimation(
                            parent: _animationController,
                            curve: const Interval(0.3, 0.8, curve: Curves.easeOut),
                          ),
                        ),
                        child: Text(
                          localizations.welcomeToIfrcNetworkDatabank,
                          style: Theme.of(context).textTheme.displayMedium?.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.bold,
                              ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),
                    // Description with fade animation
                    FadeTransition(
                      opacity: _descriptionFadeAnimation,
                      child: SlideTransition(
                        position: Tween<Offset>(
                          begin: const Offset(0, 0.3),
                          end: Offset.zero,
                        ).animate(
                          CurvedAnimation(
                            parent: _animationController,
                            curve: const Interval(0.5, 1.0, curve: Curves.easeOut),
                          ),
                        ),
                        child: Text(
                          localizations.splashDescription,
                          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                                color: Colors.white70,
                              ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                    const SizedBox(height: 24),
                    // Loading indicator with fade animation
                    FadeTransition(
                      opacity: _loaderFadeAnimation,
                      child: const CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                      ),
                    ),
                    const SizedBox(height: 32),
                    // Attribution with fade animation
                    FadeTransition(
                      opacity: _attributionFadeAnimation,
                      child: Text(
                        localizations.builtByHaytham,
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.white70,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}
