import 'dart:async';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/routes.dart';
import '../../theme/splash_hero_palette.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../services/performance_service.dart';
import '../../services/launcher_shortcuts_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';
import '../../services/organization_config_service.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/splash_hero_backdrop.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen>
    with SingleTickerProviderStateMixin {
  static const int _societyCount = 191;

  late AnimationController _entrance;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..forward();
    _checkAuthAndNavigate();
  }

  @override
  void dispose() {
    _entrance.dispose();
    super.dispose();
  }

  Future<void> _openHumDatabankGithub() async {
    final uri = Uri.parse(AppConstants.humdatabankGithubRepoUrl);
    try {
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      } else {
        DebugLogger.logWarn('SPLASH', 'Cannot launch GitHub URL');
      }
    } catch (e) {
      DebugLogger.logWarn('SPLASH', 'launchUrl failed: $e');
    }
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
          return await authProvider
              .checkAuthStatus(forceRevalidate: !shouldDeferRemoteFetch)
              .timeout(authCheckTimeout);
        } on TimeoutException {
          // Log timeout but don't throw - allow app to continue
          DebugLogger.logWarn(
            'SPLASH',
            'Auth check timed out after ${authCheckTimeout.inSeconds}s - proceeding with cached auth state',
          );
          return false; // Return false on timeout
        } catch (e) {
          // Log error but don't throw - allow app to continue
          DebugLogger.logWarn(
            'SPLASH',
            'Auth check failed: $e - proceeding with cached auth state',
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
              'Proceeding to main screen - auth check continues in background',
            );
            return false; // Return false to indicate timeout occurred
          },
        );
      } catch (e) {
        // Auth check failed or timed out - proceed anyway
        DebugLogger.logInfo(
          'SPLASH',
          'Proceeding to main screen despite auth check issue: $e',
        );
      }
    } else {
      // Minimum splash duration already exceeded timeout - proceed immediately
      DebugLogger.logInfo(
        'SPLASH',
        'Minimum splash duration exceeded - proceeding to main screen',
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
    LauncherShortcutsService.markSplashFinished();
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final reduced = MediaQuery.disableAnimationsOf(context);
    final orgName = OrganizationConfigService().isInitialized
        ? OrganizationConfigService().config.app.displayName
        : 'IFRC';

    return Scaffold(
      backgroundColor: SplashHeroPalette.navy,
      body: SplashHeroBackdrop(
        child: SafeArea(
          child: AnimatedBuilder(
            animation: _entrance,
            builder: (context, _) {
              final t = reduced ? 1.0 : _entrance.value;
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(28, 36, 28, 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _BrandMark(opacity: _interval(t, 0.02, 0.42)),
                          const SizedBox(height: 28),
                          _SocietyStat(
                            count:
                                (Curves.easeOutCubic.transform(
                                          _interval(t, 0.14, 0.52),
                                        ) *
                                        _societyCount)
                                    .round(),
                            label: localizations.nationalSocieties,
                            caption: localizations.oneDatabase,
                            opacity: _interval(t, 0.12, 0.4),
                          ),
                          const SizedBox(height: 18),
                          _Headline(
                            text: localizations.welcomeToIfrcNetworkDatabank,
                            accent: orgName,
                            progress: t,
                          ),
                          const SizedBox(height: 18),
                          Opacity(
                            opacity: _interval(t, 0.42, 0.72),
                            child: Text(
                              localizations.splashDescription,
                              style: const TextStyle(
                                color: SplashHeroPalette.inkBody,
                                fontSize: 15,
                                height: 1.55,
                                fontWeight: FontWeight.w400,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  Opacity(
                    opacity: _interval(t, 0.55, 0.85),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(28, 0, 28, 8),
                      child: AppLoadingIndicator(
                        color: SplashHeroPalette.ink.withValues(alpha: 0.85),
                        size: 18,
                      ),
                    ),
                  ),
                  Opacity(
                    opacity: _interval(t, 0.62, 0.92),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(28, 0, 28, 18),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            localizations.poweredByHumDatabank,
                            style: TextStyle(
                              color: SplashHeroPalette.ink.withValues(
                                alpha: 0.9,
                              ),
                              fontSize: 13,
                              fontWeight: FontWeight.w500,
                              letterSpacing: 0.2,
                            ),
                          ),
                          const SizedBox(height: 10),
                          Material(
                            color: SplashHeroPalette.ink,
                            elevation: 3,
                            shadowColor: SplashHeroPalette.shadow.withValues(
                              alpha: 0.45,
                            ),
                            shape: const StadiumBorder(),
                            clipBehavior: Clip.antiAlias,
                            child: InkWell(
                              onTap: _openHumDatabankGithub,
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 18,
                                  vertical: 11,
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    const FaIcon(
                                      FontAwesomeIcons.github,
                                      size: 18,
                                      color: SplashHeroPalette.navy,
                                    ),
                                    const SizedBox(width: 8),
                                    Text(
                                      localizations.openOnGithub,
                                      style: const TextStyle(
                                        color: SplashHeroPalette.navy,
                                        fontWeight: FontWeight.w700,
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
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

double _interval(double t, double start, double end) {
  if (t <= start) return 0;
  if (t >= end) return 1;
  return (t - start) / (end - start);
}

class _BrandMark extends StatelessWidget {
  const _BrandMark({required this.opacity});

  final double opacity;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: opacity.clamp(0, 1),
      child: Container(
        width: 156,
        decoration: BoxDecoration(
          color: SplashHeroPalette.ink,
          boxShadow: [
            BoxShadow(
              color: SplashHeroPalette.shadow.withValues(alpha: 0.28),
              blurRadius: 28,
              offset: const Offset(0, 12),
            ),
          ],
        ),
        child: IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const SizedBox(
                width: 4,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [
                        SplashHeroPalette.blue,
                        SplashHeroPalette.navy,
                        SplashHeroPalette.red,
                      ],
                    ),
                  ),
                ),
              ),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(10, 12, 12, 12),
                  child: Image.asset(
                    'assets/images/app_icon.png',
                    fit: BoxFit.contain,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SocietyStat extends StatelessWidget {
  const _SocietyStat({
    required this.count,
    required this.label,
    required this.caption,
    required this.opacity,
  });

  final int count;
  final String label;
  final String caption;
  final double opacity;

  @override
  Widget build(BuildContext context) {
    return Opacity(
      opacity: opacity,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text(
            '$count',
            style: const TextStyle(
              color: SplashHeroPalette.ink,
              fontSize: 44,
              fontWeight: FontWeight.w800,
              height: 1,
              letterSpacing: -1.2,
              fontFeatures: [FontFeature.tabularFigures()],
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label.toUpperCase(),
                  style: const TextStyle(
                    color: SplashHeroPalette.inkLabel,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.7,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  caption,
                  style: TextStyle(
                    color: SplashHeroPalette.ink.withValues(alpha: 0.5),
                    fontSize: 13,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline({
    required this.text,
    required this.accent,
    required this.progress,
  });

  final String text;
  final String accent;
  final double progress;

  @override
  Widget build(BuildContext context) {
    final words = text
        .split(RegExp(r'\s+'))
        .where((w) => w.isNotEmpty)
        .toList();
    final lower = text.toLowerCase();
    final accentStart = accent.isEmpty
        ? -1
        : lower.indexOf(accent.toLowerCase());
    final accentEnd = accentStart < 0 ? -1 : accentStart + accent.length;
    var cursor = 0;
    final children = <Widget>[];
    for (var i = 0; i < words.length; i++) {
      final word = words[i];
      final start = lower.indexOf(word.toLowerCase(), cursor);
      final wordStart = start < 0 ? cursor : start;
      final overlapsAccent =
          accentStart >= 0 &&
          wordStart < accentEnd &&
          wordStart + word.length > accentStart;
      children.add(
        _HeadlineWord(
          word: word,
          accent: overlapsAccent,
          shown: _interval(progress, 0.22 + i * 0.035, 0.48 + i * 0.035),
        ),
      );
      cursor = wordStart + word.length;
    }
    return Wrap(spacing: 6, runSpacing: 2, children: children);
  }
}

class _HeadlineWord extends StatelessWidget {
  const _HeadlineWord({
    required this.word,
    required this.accent,
    required this.shown,
  });

  final String word;
  final bool accent;
  final double shown;

  @override
  Widget build(BuildContext context) {
    final style = const TextStyle(
      color: SplashHeroPalette.ink,
      fontSize: 28,
      height: 1.15,
      fontWeight: FontWeight.w800,
      letterSpacing: -0.3,
    );
    Widget text = Text(word, style: style);
    if (accent) {
      text = ShaderMask(
        shaderCallback: (bounds) => const LinearGradient(
          colors: [SplashHeroPalette.redLight, SplashHeroPalette.red],
        ).createShader(bounds),
        child: Text(word, style: style),
      );
    }
    return Opacity(opacity: shown.clamp(0, 1), child: text);
  }
}
