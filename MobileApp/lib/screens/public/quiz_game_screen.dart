import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../models/public/quiz_question.dart';
import '../../providers/public/quiz_game_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../config/routes.dart';
import '../../widgets/error_state.dart';
import '../../widgets/loading_indicator.dart';

class QuizGameScreen extends StatefulWidget {
  const QuizGameScreen({super.key});

  @override
  State<QuizGameScreen> createState() => _QuizGameScreenState();
}

class _QuizGameScreenState extends State<QuizGameScreen>
    with TickerProviderStateMixin {
  late AnimationController _questionAnimationController;
  late AnimationController _progressAnimationController;
  late AnimationController _feedbackAnimationController;
  late AnimationController _scoreAnimationController;
  late AnimationController _definitionAnimationController;
  late AnimationController _splashAnimationController;
  late Animation<double> _questionSlideAnimation;
  late Animation<double> _progressAnimation;
  late Animation<double> _feedbackScaleAnimation;
  late Animation<double> _scoreScaleAnimation;
  late Animation<double> _definitionFadeAnimation;
  late Animation<double> _splashFadeAnimation;
  late Animation<double> _splashScaleAnimation;
  int _previousQuestionIndex = -1;
  bool _showSplash = true;
  bool _gameStarted = false;

  @override
  void initState() {
    super.initState();

    // Question slide animation
    _questionAnimationController = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );
    _questionSlideAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _questionAnimationController,
        curve: Curves.easeOutCubic,
      ),
    );

    // Progress animation
    _progressAnimationController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );
    _progressAnimation = CurvedAnimation(
      parent: _progressAnimationController,
      curve: Curves.easeOut,
    );

    // Feedback scale animation
    _feedbackAnimationController = AnimationController(
      duration: const Duration(milliseconds: 300),
      vsync: this,
    );
    _feedbackScaleAnimation = Tween<double>(begin: 0.8, end: 1.0).animate(
      CurvedAnimation(
        parent: _feedbackAnimationController,
        curve: Curves.elasticOut,
      ),
    );

    // Score animation
    _scoreAnimationController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );
    _scoreScaleAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _scoreAnimationController,
        curve: Curves.elasticOut,
      ),
    );

    // Definition fade animation
    _definitionAnimationController = AnimationController(
      duration: const Duration(milliseconds: 500),
      vsync: this,
    );
    _definitionFadeAnimation = CurvedAnimation(
      parent: _definitionAnimationController,
      curve: Curves.easeIn,
    );

    // Splash screen animation
    _splashAnimationController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );
    _splashFadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(
        parent: _splashAnimationController,
        curve: const Interval(0.0, 0.6, curve: Curves.easeIn),
      ),
    );
    _splashScaleAnimation = Tween<double>(begin: 0.5, end: 1.0).animate(
      CurvedAnimation(
        parent: _splashAnimationController,
        curve: Curves.elasticOut,
      ),
    );

    // Set full screen mode
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.immersiveSticky);

    // Show splash screen
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _splashAnimationController.forward();
    });
  }

  @override
  void dispose() {
    // Restore system UI
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);

    _questionAnimationController.dispose();
    _progressAnimationController.dispose();
    _feedbackAnimationController.dispose();
    _scoreAnimationController.dispose();
    _definitionAnimationController.dispose();
    _splashAnimationController.dispose();
    super.dispose();
  }

  void _handleQuestionChange(QuizGameProvider quizProvider) {
    if (_previousQuestionIndex != quizProvider.currentQuestionIndex) {
      _previousQuestionIndex = quizProvider.currentQuestionIndex;
      _questionAnimationController.reset();
      _questionAnimationController.forward();
      _progressAnimationController.reset();
      _progressAnimationController.forward();
      _definitionAnimationController.reset();
    }
  }

  void _handleAnswerSelection(QuizGameProvider quizProvider, String answer) {
    HapticFeedback.selectionClick();
    quizProvider.selectAnswer(answer);
    if (quizProvider.isCorrect) {
      HapticFeedback.mediumImpact();
    } else {
      HapticFeedback.heavyImpact();
    }
    _feedbackAnimationController.reset();
    _feedbackAnimationController.forward();

    // Show definition after a short delay
    Future.delayed(const Duration(milliseconds: 300), () {
      if (mounted && quizProvider.showResult) {
        _definitionAnimationController.forward();
      }
    });
  }

  Future<void> _startGame() async {
    if (mounted) {
      setState(() {
        _showSplash = false;
      });

      final quizProvider = Provider.of<QuizGameProvider>(
        context,
        listen: false,
      );
      if (!quizProvider.isQuizActive && !_gameStarted) {
        _gameStarted = true;
        await quizProvider.startQuiz();
      }
      if (mounted) {
        _progressAnimationController.forward();
        _scoreAnimationController.forward();
        _questionAnimationController.forward();
      }
    }
  }

  void _exitQuiz(BuildContext context) {
    HapticFeedback.lightImpact();
    SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    final nav = Navigator.of(context, rootNavigator: true);
    if (nav.canPop()) {
      nav.pop();
      return;
    }
    nav.pushNamedAndRemoveUntil(
      AppRoutes.dashboard,
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          // Main content
          Consumer<QuizGameProvider>(
            builder: (context, quizProvider, child) {
              // Handle question changes
              if (quizProvider.isQuizActive &&
                  quizProvider.currentQuestionIndex >= 0 &&
                  _previousQuestionIndex != quizProvider.currentQuestionIndex) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  _handleQuestionChange(quizProvider);
                });
              }

              // Handle feedback animation when result is shown
              if (quizProvider.showResult &&
                  _feedbackAnimationController.status !=
                      AnimationStatus.forward &&
                  _feedbackAnimationController.status !=
                      AnimationStatus.completed) {
                WidgetsBinding.instance.addPostFrameCallback((_) {
                  _feedbackAnimationController.forward();
                });
              }

              // Ensure animations are running when quiz is active
              if (quizProvider.isQuizActive &&
                  quizProvider.currentIndicator != null &&
                  !_questionAnimationController.isAnimating &&
                  _questionAnimationController.value < 1.0) {
                _questionAnimationController.forward();
              }

              if (quizProvider.isLoading) {
                return _buildLoadingScreen(context, theme, localizations);
              }

              if (quizProvider.error != null) {
                return _buildErrorScreen(
                  context,
                  quizProvider,
                  theme,
                  localizations,
                );
              }

              if (quizProvider.isQuizComplete) {
                return _buildQuizComplete(
                  context,
                  quizProvider,
                  theme,
                  localizations,
                );
              }

              if (!quizProvider.isQuizActive ||
                  quizProvider.currentIndicator == null) {
                return _buildStartScreen(
                  context,
                  quizProvider,
                  theme,
                  localizations,
                );
              }

              return _buildQuizQuestion(
                context,
                quizProvider,
                theme,
                localizations,
              );
            },
          ),

          // Splash screen overlay
          if (_showSplash) _buildSplashScreen(context, theme, localizations),

          // Above splash + content so close is always visible (splash is full-screen).
          // Single exit control — no duplicate in question HUD.
          // IconButton + root navigator: reliable hit target; maybePop() was a no-op
          // when canPop was false; nested navigators could also block the default pop.
          Positioned(
            top: MediaQuery.paddingOf(context).top + 4,
            left: 4,
            child: IconButton(
              tooltip: localizations.close,
              onPressed: () => _exitQuiz(context),
              style: IconButton.styleFrom(
                backgroundColor: theme.colorScheme.surface.withValues(
                  alpha: 0.94,
                ),
                foregroundColor: context.textColor,
                padding: const EdgeInsets.all(10),
                minimumSize: const Size(44, 44),
                tapTargetSize: MaterialTapTargetSize.padded,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                  side: BorderSide(
                    color: theme.colorScheme.primary.withValues(alpha: 0.35),
                    width: 1.5,
                  ),
                ),
                elevation: 2,
                shadowColor: theme.ambientShadow(
                  lightOpacity: 0.12,
                  darkOpacity: 0.45,
                ),
              ),
              icon: const Icon(Icons.close_rounded, size: 22),
            ),
          ),
        ],
      ),
    );
  }

  Widget _splashAmbientOrb({
    required Color centerColor,
    required double diameter,
    double maxOpacity = 0.18,
  }) {
    return IgnorePointer(
      child: Container(
        width: diameter,
        height: diameter,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [
              centerColor.withValues(alpha: maxOpacity),
              centerColor.withValues(alpha: 0),
            ],
          ),
        ),
      ),
    );
  }

  Widget _splashDecorChip(IconData icon, Color onPrimary) {
    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: onPrimary.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: onPrimary.withValues(alpha: 0.22),
        ),
      ),
      child: Icon(
        icon,
        size: 22,
        color: onPrimary.withValues(alpha: 0.9),
      ),
    );
  }

  Widget _buildSplashScreen(
    BuildContext context,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    final scheme = theme.colorScheme;
    final onP = scheme.onPrimary;
    final primary = scheme.primary;
    final secondary = scheme.secondary;
    final tertiary = scheme.tertiary;
    final shadow = theme.ambientShadow(
      lightOpacity: 0.28,
      darkOpacity: 0.42,
    );

    return Stack(
      fit: StackFit.expand,
      clipBehavior: Clip.none,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              stops: const [0.0, 0.32, 0.58, 1.0],
              colors: [
                Color.lerp(primary, secondary, 0.25)!,
                primary,
                Color.lerp(secondary, tertiary, 0.4)!,
                Color.lerp(tertiary, primary, 0.35)!,
              ],
            ),
          ),
        ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                stops: const [0.55, 1.0],
                colors: [
                  Colors.transparent,
                  Colors.black.withValues(
                    alpha: theme.isDarkTheme ? 0.26 : 0.1,
                  ),
                ],
              ),
            ),
          ),
        ),
        Positioned(
          top: -48,
          right: -36,
          child: _splashAmbientOrb(
            centerColor: onP,
            diameter: 240,
            maxOpacity: 0.22,
          ),
        ),
        Positioned(
          bottom: 80,
          left: -56,
          child: _splashAmbientOrb(
            centerColor: secondary,
            diameter: 200,
            maxOpacity: 0.16,
          ),
        ),
        Positioned(
          top: 160,
          left: -20,
          child: _splashAmbientOrb(
            centerColor: tertiary,
            diameter: 140,
            maxOpacity: 0.12,
          ),
        ),
        Positioned.fill(
          child: CustomPaint(
            painter: _SplashPatternPainter(accent: onP),
          ),
        ),
        FadeTransition(
          opacity: _splashFadeAnimation,
          child: ScaleTransition(
            scale: _splashScaleAnimation,
            child: SafeArea(
              child: Align(
                alignment: Alignment.center,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 420),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(32),
                      child: BackdropFilter(
                        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.fromLTRB(22, 32, 22, 28),
                          decoration: BoxDecoration(
                            color: onP.withValues(alpha: 0.13),
                            borderRadius: BorderRadius.circular(32),
                            border: Border.all(
                              color: onP.withValues(alpha: 0.42),
                              width: 1.5,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.2),
                                blurRadius: 40,
                                offset: const Offset(0, 24),
                              ),
                              BoxShadow(
                                color: onP.withValues(alpha: 0.12),
                                blurRadius: 0,
                                spreadRadius: 1,
                              ),
                            ],
                          ),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                padding: const EdgeInsets.all(3),
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  gradient: LinearGradient(
                                    begin: Alignment.topLeft,
                                    end: Alignment.bottomRight,
                                    colors: [
                                      onP.withValues(alpha: 0.95),
                                      onP.withValues(alpha: 0.25),
                                    ],
                                  ),
                                  boxShadow: [
                                    BoxShadow(
                                      color: onP.withValues(alpha: 0.35),
                                      blurRadius: 28,
                                      spreadRadius: 0,
                                    ),
                                  ],
                                ),
                                child: Container(
                                  padding: const EdgeInsets.all(20),
                                  decoration: BoxDecoration(
                                    color: theme.isDarkTheme
                                        ? scheme.surfaceContainerHighest
                                            .withValues(alpha: 0.96)
                                        : Colors.white,
                                    shape: BoxShape.circle,
                                  ),
                                  child: ShaderMask(
                                    blendMode: BlendMode.srcIn,
                                    shaderCallback: (bounds) =>
                                        LinearGradient(
                                      colors: [primary, tertiary],
                                      begin: Alignment.topLeft,
                                      end: Alignment.bottomRight,
                                    ).createShader(bounds),
                                    child: const Icon(
                                      Icons.quiz_rounded,
                                      size: 54,
                                      color: Colors.white,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 22),
                              Text(
                                localizations.quizGameTitle,
                                textAlign: TextAlign.center,
                                style: theme.textTheme.headlineMedium?.copyWith(
                                  color: onP,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.5,
                                  height: 1.15,
                                  shadows: [
                                    Shadow(
                                      color: shadow,
                                      blurRadius: 14,
                                      offset: const Offset(0, 2),
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 12),
                              Container(
                                width: 48,
                                height: 4,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(999),
                                  gradient: LinearGradient(
                                    colors: [
                                      onP,
                                      onP.withValues(alpha: 0.2),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: 14),
                              Text(
                                localizations.quizGameTestYourKnowledge,
                                textAlign: TextAlign.center,
                                style: theme.textTheme.titleMedium?.copyWith(
                                  color: onP.withValues(alpha: 0.92),
                                  fontWeight: FontWeight.w500,
                                  height: 1.35,
                                  shadows: [
                                    Shadow(
                                      color: shadow.withValues(alpha: 0.65),
                                      blurRadius: 10,
                                    ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 22),
                              Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  _splashDecorChip(
                                    Icons.insights_outlined,
                                    onP,
                                  ),
                                  const SizedBox(width: 12),
                                  _splashDecorChip(
                                    Icons.public_rounded,
                                    onP,
                                  ),
                                  const SizedBox(width: 12),
                                  _splashDecorChip(
                                    Icons.auto_awesome_rounded,
                                    onP,
                                  ),
                                ],
                              ),
                              const SizedBox(height: 32),
                              Selector<AuthProvider, bool>(
                                selector: (_, auth) => auth.isAuthenticated,
                                builder: (context, isAuthenticated, _) {
                                  return LayoutBuilder(
                                    builder: (context, constraints) {
                                      final maxW = constraints.maxWidth;
                                      final useFullWidthButtons = maxW < 360;
                                      Widget leaderboardBtn() =>
                                          ElevatedButton.icon(
                                            onPressed: () {
                                              Navigator.of(context).pushNamed(
                                                AppRoutes.leaderboard,
                                              );
                                            },
                                            icon: const Icon(
                                              Icons.leaderboard_rounded,
                                              size: 20,
                                            ),
                                            label: Text(
                                              localizations
                                                  .quizGameViewLeaderboard,
                                              style: const TextStyle(
                                                fontSize: 14,
                                                fontWeight: FontWeight.bold,
                                              ),
                                              maxLines: 2,
                                              textAlign: TextAlign.center,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                            style: ElevatedButton.styleFrom(
                                              padding:
                                                  const EdgeInsets.symmetric(
                                                horizontal: 20,
                                                vertical: 15,
                                              ),
                                              backgroundColor: onP.withValues(
                                                alpha: 0.18,
                                              ),
                                              foregroundColor: onP,
                                              side: BorderSide(
                                                color: onP.withValues(
                                                  alpha: 0.85,
                                                ),
                                                width: 1.5,
                                              ),
                                              shape: RoundedRectangleBorder(
                                                borderRadius:
                                                    BorderRadius.circular(16),
                                              ),
                                              elevation: 3,
                                              shadowColor: theme.ambientShadow(
                                                lightOpacity: 0.2,
                                                darkOpacity: 0.4,
                                              ),
                                            ),
                                          );
                                      Widget startBtn() => ElevatedButton.icon(
                                            onPressed: _startGame,
                                            icon: const Icon(
                                              Icons.play_arrow_rounded,
                                              size: 26,
                                            ),
                                            label: Text(
                                              localizations.quizGameStartQuiz,
                                              style: const TextStyle(
                                                fontSize: 16,
                                                fontWeight: FontWeight.bold,
                                              ),
                                              maxLines: 2,
                                              textAlign: TextAlign.center,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                            style: ElevatedButton.styleFrom(
                                              padding:
                                                  const EdgeInsets.symmetric(
                                                horizontal: 28,
                                                vertical: 16,
                                              ),
                                              backgroundColor: theme.isDarkTheme
                                                  ? scheme
                                                      .surfaceContainerHighest
                                                  : scheme.surface,
                                              foregroundColor:
                                                  context.navyForegroundColor,
                                              shape: RoundedRectangleBorder(
                                                borderRadius:
                                                    BorderRadius.circular(16),
                                              ),
                                              elevation: 5,
                                              shadowColor: theme.ambientShadow(
                                                lightOpacity: 0.22,
                                                darkOpacity: 0.45,
                                              ),
                                            ),
                                          );
                                      if (useFullWidthButtons) {
                                        return Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.stretch,
                                          children: [
                                            if (isAuthenticated) ...[
                                              leaderboardBtn(),
                                              const SizedBox(height: 12),
                                            ],
                                            startBtn(),
                                          ],
                                        );
                                      }
                                      return Wrap(
                                        alignment: WrapAlignment.center,
                                        crossAxisAlignment:
                                            WrapCrossAlignment.center,
                                        spacing: 16,
                                        runSpacing: 12,
                                        children: [
                                          if (isAuthenticated) leaderboardBtn(),
                                          startBtn(),
                                        ],
                                      );
                                    },
                                  );
                                },
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildLoadingScreen(
    BuildContext context,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 32, horizontal: 28),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(
              color: theme.colorScheme.primary.withValues(alpha: 0.4),
              width: 2,
            ),
            color: theme.colorScheme.surface.withValues(alpha: 0.85),
            boxShadow: [
              BoxShadow(
                color: theme.colorScheme.primary.withValues(alpha: 0.12),
                blurRadius: 20,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          child: AppLoadingIndicator(
            message: localizations.quizGameLoading,
            color: theme.colorScheme.primary,
            size: 26,
            useIOSStyle: false,
          ),
        ),
      ),
    );
  }

  Widget _buildErrorScreen(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: AppErrorState(
        showTitle: false,
        message: quizProvider.error!,
        icon: Icons.error_outline_rounded,
        iconColor: theme.colorScheme.error,
        onRetry: () => quizProvider.startQuiz(),
        retryLabel: localizations.quizGameTryAgain,
        retryStyle: AppErrorRetryStyle.materialFilled,
      ),
    );
  }

  Widget _buildStartScreen(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    return Center(
      child: ElevatedButton(
        onPressed: () => quizProvider.startQuiz(),
        style: ElevatedButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
        ),
        child: Text(localizations.quizGameStartQuiz),
      ),
    );
  }

  Widget _buildGameHud(
    BuildContext context,
    ThemeData theme,
    QuizGameProvider quizProvider,
  ) {
    final accent = theme.colorScheme.primary;
    final streak = quizProvider.answerStreak;
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface.withValues(alpha: 0.92),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: accent.withValues(alpha: 0.65), width: 2),
            boxShadow: [
              BoxShadow(
                color: accent.withValues(alpha: 0.22),
                blurRadius: 12,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.sports_esports_rounded, size: 20, color: accent),
              const SizedBox(width: 6),
              Text(
                '${quizProvider.currentQuestionIndex + 1}/${quizProvider.totalQuestions}',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.5,
                  color: context.textColor,
                ),
              ),
            ],
          ),
        ),
        const Spacer(),
        if (streak >= 2)
          Container(
            margin: const EdgeInsets.only(right: 8),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [Colors.orange.shade600, Colors.deepOrange.shade400],
              ),
              borderRadius: BorderRadius.circular(20),
              boxShadow: [
                BoxShadow(
                  color: Colors.orange.withValues(alpha: 0.45),
                  blurRadius: 8,
                ),
              ],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.local_fire_department_rounded,
                  size: 18,
                  color: Colors.white,
                ),
                const SizedBox(width: 4),
                Text(
                  '$streak',
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ],
            ),
          ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: theme.colorScheme.surfaceContainerHighest.withValues(
              alpha: 0.95,
            ),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: theme.colorScheme.outline.withValues(alpha: 0.25),
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.stars_rounded,
                color: Color(AppConstants.warningColor),
                size: 22,
              ),
              const SizedBox(width: 6),
              Text(
                '${quizProvider.score}',
                style: theme.textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w900,
                  color: context.textColor,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildGameProgressSegments(
    BuildContext context,
    ThemeData theme,
    QuizGameProvider quizProvider,
  ) {
    final total = quizProvider.totalQuestions;
    final idx = quizProvider.currentQuestionIndex;
    final accent = theme.colorScheme.primary;
    final track = context.lightSurfaceColor;

    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: AnimatedBuilder(
        animation: _progressAnimation,
        builder: (context, child) {
          return Row(
            children: List.generate(total, (i) {
              final isDone = i < idx;
              final isCurrent = i == idx;
              late Color fill;
              BoxBorder? border;
              List<BoxShadow>? glow;
              if (isDone) {
                fill = accent;
                border = Border.all(
                  color: accent.withValues(alpha: 0.95),
                  width: 1.5,
                );
              } else if (isCurrent) {
                fill = Color.lerp(
                  track,
                  accent,
                  0.35 + 0.45 * _progressAnimation.value,
                )!;
                border = Border.all(color: accent, width: 2);
                glow = [
                  BoxShadow(
                    color: accent.withValues(alpha: 0.45),
                    blurRadius: 8,
                  ),
                ];
              } else {
                fill = track;
                border = Border.all(
                  color: theme.colorScheme.outline.withValues(alpha: 0.22),
                );
              }
              return Expanded(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 2),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 220),
                    height: 9,
                    decoration: BoxDecoration(
                      color: fill,
                      borderRadius: BorderRadius.circular(4),
                      border: border,
                      boxShadow: glow,
                    ),
                  ),
                ),
              );
            }),
          );
        },
      ),
    );
  }

  Widget _buildQuizQuestion(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    final indicator = quizProvider.currentIndicator!;
    final currentQuestion =
        quizProvider.questions[quizProvider.currentQuestionIndex];
    final questionText = currentQuestion.questionType == QuizQuestionType.sector
        ? localizations.quizGameWhichSector
        : localizations.quizGameWhichSubsector;

    final accent = theme.colorScheme.primary;

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.scaffoldBackgroundColor,
            accent.withValues(alpha: 0.07),
            theme.colorScheme.tertiary.withValues(alpha: 0.05),
          ],
          stops: const [0.0, 0.5, 1.0],
        ),
      ),
      child: CustomPaint(
        painter: _BackgroundPatternPainter(theme),
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(52, 4, 16, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildGameHud(context, theme, quizProvider),
                    _buildGameProgressSegments(context, theme, quizProvider),
                  ],
                ),
              ),
              Expanded(
                child:
                    quizProvider.questions.isEmpty ||
                        quizProvider.currentIndicator == null
                    ? const Center(child: CircularProgressIndicator())
                    : SlideTransition(
                        position:
                            Tween<Offset>(
                              begin: const Offset(0.22, 0.0),
                              end: Offset.zero,
                            ).animate(
                              CurvedAnimation(
                                parent: _questionAnimationController,
                                curve: Curves.easeOutCubic,
                              ),
                            ),
                        child: FadeTransition(
                          opacity: _questionSlideAnimation,
                          child: SingleChildScrollView(
                            padding: const EdgeInsets.fromLTRB(20, 12, 20, 24),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Container(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                    vertical: 6,
                                  ),
                                  decoration: BoxDecoration(
                                    color: accent.withValues(alpha: 0.12),
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(
                                      color: accent.withValues(alpha: 0.35),
                                    ),
                                  ),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      Icon(
                                        Icons.flag_rounded,
                                        size: 18,
                                        color: accent,
                                      ),
                                      const SizedBox(width: 8),
                                      Flexible(
                                        child: Text(
                                          questionText,
                                          style: theme.textTheme.titleMedium
                                              ?.copyWith(
                                                fontWeight: FontWeight.w800,
                                                color: context.textColor,
                                                height: 1.25,
                                              ),
                                          textAlign: TextAlign.center,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                const SizedBox(height: 18),
                                Container(
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(14),
                                    gradient: LinearGradient(
                                      colors: [
                                        accent.withValues(alpha: 0.55),
                                        theme.colorScheme.secondary.withValues(
                                          alpha: 0.45,
                                        ),
                                      ],
                                    ),
                                    boxShadow: [
                                      BoxShadow(
                                        color: accent.withValues(alpha: 0.18),
                                        blurRadius: 18,
                                        offset: const Offset(0, 6),
                                      ),
                                    ],
                                  ),
                                  padding: const EdgeInsets.all(2),
                                  child: Container(
                                    padding: const EdgeInsets.all(14),
                                    decoration: BoxDecoration(
                                      color: theme.cardColor,
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          indicator.displayName,
                                          style: theme.textTheme.titleMedium
                                              ?.copyWith(
                                                fontWeight: FontWeight.w800,
                                                color: context.textColor,
                                                height: 1.25,
                                              ),
                                        ),
                                        if (quizProvider.showResult) ...[
                                          const SizedBox(height: 12),
                                          FadeTransition(
                                            opacity: _definitionFadeAnimation,
                                            child: Container(
                                              width: double.infinity,
                                              padding: const EdgeInsets.all(12),
                                              decoration: BoxDecoration(
                                                color: theme
                                                    .colorScheme
                                                    .surfaceContainerHighest,
                                                borderRadius:
                                                    BorderRadius.circular(8),
                                                border: Border.all(
                                                  color: theme
                                                      .colorScheme
                                                      .outline
                                                      .withValues(alpha: 0.15),
                                                ),
                                              ),
                                              child: Column(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Row(
                                                    children: [
                                                      Icon(
                                                        Icons.info_outline,
                                                        size: 16,
                                                        color: context
                                                            .navyIconColor,
                                                      ),
                                                      const SizedBox(width: 6),
                                                      Text(
                                                        localizations
                                                            .quizGameDefinition,
                                                        style: theme
                                                            .textTheme
                                                            .bodyMedium
                                                            ?.copyWith(
                                                              fontWeight:
                                                                  FontWeight
                                                                      .bold,
                                                              color: context
                                                                  .navyTextColor,
                                                            ),
                                                      ),
                                                    ],
                                                  ),
                                                  const SizedBox(height: 8),
                                                  Text(
                                                    indicator
                                                            .localizedDefinition ??
                                                        indicator.definition ??
                                                        localizations
                                                            .quizGameNoDefinition,
                                                    style: theme
                                                        .textTheme
                                                        .bodyMedium
                                                        ?.copyWith(
                                                          color: context
                                                              .textSecondaryColor,
                                                          height: 1.5,
                                                        ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ),
                                        ],
                                      ],
                                    ),
                                  ),
                                ),
                                const SizedBox(height: 18),
                                ...quizProvider.options.asMap().entries.map((
                                  entry,
                                ) {
                                  final index = entry.key;
                                  final option = entry.value;
                                  return TweenAnimationBuilder<double>(
                                    duration: Duration(
                                      milliseconds: 260 + (index * 70),
                                    ),
                                    tween: Tween<double>(begin: 0.0, end: 1.0),
                                    curve: Curves.easeOut,
                                    builder: (context, value, child) {
                                      return Transform.translate(
                                        offset: Offset(0, 16 * (1 - value)),
                                        child: Opacity(
                                          opacity: value,
                                          child: child,
                                        ),
                                      );
                                    },
                                    child: _buildOptionButton(
                                      context,
                                      option,
                                      index,
                                      quizProvider,
                                      theme,
                                    ),
                                  );
                                }),
                              ],
                            ),
                          ),
                        ),
                      ),
              ),
              if (quizProvider.showResult)
                _buildResultFeedback(
                  context,
                  quizProvider,
                  theme,
                  localizations,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildOptionButton(
    BuildContext context,
    String option,
    int optionIndex,
    QuizGameProvider quizProvider,
    ThemeData theme,
  ) {
    final isSelected = quizProvider.selectedAnswer == option;
    final showResult = quizProvider.showResult;
    final isCorrect = option == quizProvider.correctAnswer;
    final isWrong = isSelected && !isCorrect;
    final letter = String.fromCharCode(65 + optionIndex.clamp(0, 25));

    return Padding(
      padding: const EdgeInsets.only(bottom: 10.0),
      child: TweenAnimationBuilder<double>(
        duration: const Duration(milliseconds: 200),
        tween: Tween<double>(begin: 1.0, end: isSelected ? 1.015 : 1.0),
        builder: (context, scale, child) {
          return Transform.scale(
            scale: scale,
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: showResult
                    ? null
                    : () => _handleAnswerSelection(quizProvider, option),
                borderRadius: BorderRadius.circular(12),
                child: Ink(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 14,
                  ),
                  decoration: BoxDecoration(
                    color: _getOptionColor(
                      context,
                      theme,
                      showResult,
                      isCorrect,
                      isWrong,
                      isSelected,
                    ),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: _getOptionBorderColor(
                        theme,
                        showResult,
                        isCorrect,
                        isWrong,
                        isSelected,
                      ),
                      width: showResult && (isCorrect || isWrong) ? 2 : 1.5,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: _getOptionShadowColor(
                          theme,
                          showResult,
                          isCorrect,
                          isWrong,
                          isSelected,
                        ),
                        blurRadius: isSelected ? 8 : 4,
                        spreadRadius: isSelected ? 1 : 0,
                        offset: Offset(0, isSelected ? 3 : 1),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          color: _getOptionIconBackgroundColor(
                            theme,
                            showResult,
                            isCorrect,
                            isWrong,
                            isSelected,
                          ),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: theme.colorScheme.outline.withValues(
                              alpha: 0.12,
                            ),
                          ),
                        ),
                        child: showResult
                            ? Icon(
                                _getOptionIcon(
                                  showResult,
                                  isCorrect,
                                  isWrong,
                                  isSelected,
                                ),
                                color: _getOptionIconColor(
                                  theme,
                                  showResult,
                                  isCorrect,
                                  isWrong,
                                  isSelected,
                                ),
                                size: 22,
                              )
                            : Text(
                                letter,
                                style: theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.w900,
                                  color: theme.colorScheme.primary,
                                ),
                              ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          option,
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: _getOptionTextColor(
                              context,
                              theme,
                              showResult,
                              isCorrect,
                              isWrong,
                              isSelected,
                            ),
                            fontWeight: isSelected || (showResult && isCorrect)
                                ? FontWeight.w700
                                : FontWeight.w500,
                            height: 1.25,
                          ),
                        ),
                      ),
                      if (showResult && isCorrect)
                        ScaleTransition(
                          scale: _feedbackScaleAnimation,
                          child: const Icon(
                            Icons.check_circle,
                            color: Color(AppConstants.successColor),
                            size: 24,
                          ),
                        ),
                      if (showResult && isWrong)
                        ScaleTransition(
                          scale: _feedbackScaleAnimation,
                          child: const Icon(
                            Icons.cancel,
                            color: Color(AppConstants.errorColor),
                            size: 24,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Color _getOptionColor(
    BuildContext context,
    ThemeData theme,
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return theme.quizOptionResultCorrectFill();
      } else if (isWrong) {
        return theme.quizOptionResultWrongFill();
      } else {
        return context.cardColor.withValues(alpha: 0.5);
      }
    } else {
      return isSelected
          ? theme.colorScheme.primaryContainer.withValues(alpha: 0.7)
          : context.cardColor;
    }
  }

  Color _getOptionBorderColor(
    ThemeData theme,
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return theme.quizOptionResultCorrectBorder();
      } else if (isWrong) {
        return theme.quizOptionResultWrongBorder();
      } else {
        return Colors.transparent;
      }
    } else {
      return isSelected
          ? theme.colorScheme.primary
          : theme.colorScheme.outline.withValues(alpha: 0.2);
    }
  }

  Color _getOptionShadowColor(
    ThemeData theme,
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return theme.quizOptionResultShadow(true, false);
      } else if (isWrong) {
        return theme.quizOptionResultShadow(false, true);
      }
    } else if (isSelected) {
      return theme.colorScheme.primary.withValues(alpha: 0.4);
    }
    return theme.ambientShadow(lightOpacity: 0.1, darkOpacity: 0.35);
  }

  Color _getOptionIconBackgroundColor(
    ThemeData theme,
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return theme.quizOptionResultCorrectIconBg();
      } else if (isWrong) {
        return theme.quizOptionResultWrongIconBg();
      }
    }
    return theme.colorScheme.surfaceContainerHighest;
  }

  IconData _getOptionIcon(
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return Icons.check_circle;
      } else if (isWrong) {
        return Icons.cancel;
      }
    }
    return Icons.radio_button_unchecked;
  }

  Color _getOptionIconColor(
    ThemeData theme,
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return theme.quizOptionResultCorrectIconFg();
      } else if (isWrong) {
        return theme.quizOptionResultWrongIconFg();
      }
    }
    return theme.colorScheme.primary;
  }

  Color _getOptionTextColor(
    BuildContext context,
    ThemeData theme,
    bool showResult,
    bool isCorrect,
    bool isWrong,
    bool isSelected,
  ) {
    if (showResult) {
      if (isCorrect) {
        return theme.quizOptionResultCorrectText();
      } else if (isWrong) {
        return theme.quizOptionResultWrongText();
      } else {
        return context.textColor.withValues(alpha: 0.5);
      }
    }
    return context.textColor;
  }

  Widget _buildResultFeedback(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    final accent = theme.colorScheme.primary;
    return ClipRRect(
      borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: double.infinity,
            height: 5,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  accent,
                  theme.colorScheme.secondary,
                  theme.colorScheme.tertiary,
                ],
              ),
            ),
          ),
          Container(
            width: double.infinity,
            decoration: BoxDecoration(
              color: context.cardColor,
              boxShadow: [
                BoxShadow(
                  color: theme.ambientShadow(),
                  blurRadius: 16,
                  offset: const Offset(0, -3),
                ),
              ],
            ),
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 10),
            child: SafeArea(
              top: false,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Feedback message with animation - styled as a badge/status indicator
                  ScaleTransition(
                    scale: _feedbackScaleAnimation,
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 8,
                      ),
                      decoration: BoxDecoration(
                        color: quizProvider.isCorrect
                            ? (theme.isDarkTheme
                                  ? Colors.green.shade900.withValues(
                                      alpha: 0.45,
                                    )
                                  : Colors.green.shade50)
                            : (theme.isDarkTheme
                                  ? Colors.red.shade900.withValues(alpha: 0.45)
                                  : Colors.red.shade50),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: quizProvider.isCorrect
                              ? (theme.isDarkTheme
                                    ? Colors.green.shade600
                                    : Colors.green.shade300)
                              : (theme.isDarkTheme
                                    ? Colors.red.shade600
                                    : Colors.red.shade300),
                          width: 1.5,
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            padding: const EdgeInsets.all(4),
                            decoration: BoxDecoration(
                              color: quizProvider.isCorrect
                                  ? const Color(AppConstants.successColor)
                                  : const Color(AppConstants.errorColor),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              quizProvider.isCorrect
                                  ? Icons.check_rounded
                                  : Icons.close_rounded,
                              color: theme.colorScheme.onPrimary,
                              size: 14,
                            ),
                          ),
                          const SizedBox(width: 8),
                          Text(
                            quizProvider.isCorrect
                                ? localizations.quizGameCorrect
                                : localizations.quizGameIncorrect,
                            style: theme.textTheme.bodyLarge?.copyWith(
                              color: quizProvider.isCorrect
                                  ? theme.quizOptionResultCorrectText()
                                  : theme.quizOptionResultWrongText(),
                              fontWeight: FontWeight.bold,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  // Next button or View Results button
                  SizedBox(
                    width: double.infinity,
                    child: quizProvider.hasMoreQuestions
                        ? ElevatedButton(
                            onPressed: () {
                              _definitionAnimationController.reset();
                              quizProvider.nextQuestion();
                            },
                            style: ElevatedButton.styleFrom(
                              padding: const EdgeInsets.symmetric(vertical: 14),
                              minimumSize: const Size(double.infinity, 48),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                              elevation: 3,
                            ),
                            child: Text(
                              localizations.quizGameNextQuestion,
                              style: const TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          )
                        : Container(
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  theme.colorScheme.primary,
                                  theme.colorScheme.secondary,
                                ],
                              ),
                              borderRadius: BorderRadius.circular(16),
                              boxShadow: [
                                BoxShadow(
                                  color: theme.colorScheme.primary.withValues(
                                    alpha: 0.4,
                                  ),
                                  blurRadius: 12,
                                  spreadRadius: 2,
                                  offset: const Offset(0, 4),
                                ),
                              ],
                            ),
                            child: ElevatedButton(
                              onPressed: () {
                                // Navigate to results screen
                                quizProvider
                                    .nextQuestion(); // This will mark quiz as complete
                              },
                              style: ElevatedButton.styleFrom(
                                padding: const EdgeInsets.symmetric(
                                  vertical: 14,
                                ),
                                minimumSize: const Size(double.infinity, 48),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                elevation: 0,
                                backgroundColor: Colors.transparent,
                                shadowColor: Colors.transparent,
                              ),
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Text(
                                    localizations.quizGameViewResults,
                                    style: TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.w800,
                                      color: theme.colorScheme.onPrimary,
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  Icon(
                                    Icons.arrow_forward_rounded,
                                    size: 18,
                                    color: theme.colorScheme.onPrimary,
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
      ),
    );
  }

  Widget _buildQuizComplete(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    final scorePercentage = quizProvider.scorePercentage;
    final isExcellent = scorePercentage >= 80;
    final isGood = scorePercentage >= 60;
    final isPass = scorePercentage >= 40;

    IconData icon;
    Color color;
    String message;
    List<Color> gradientColors;

    if (isExcellent) {
      icon = Icons.emoji_events;
      color = Colors.amber;
      message = localizations.quizGameExcellentWork;
      gradientColors = [Colors.amber.shade300, Colors.orange.shade400];
    } else if (isGood) {
      icon = Icons.thumb_up;
      color = Colors.green;
      message = localizations.quizGameWellDone;
      gradientColors = [Colors.green.shade300, Colors.teal.shade400];
    } else if (isPass) {
      icon = Icons.sentiment_satisfied;
      color = Colors.blue;
      message = localizations.quizGameGoodEffort;
      gradientColors = [Colors.blue.shade300, Colors.indigo.shade400];
    } else {
      icon = Icons.sentiment_neutral;
      color = Colors.orange;
      message = localizations.quizGameKeepPracticing;
      gradientColors = [Colors.orange.shade300, Colors.red.shade400];
    }

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.scaffoldBackgroundColor,
            gradientColors[0].withValues(alpha: 0.1),
            gradientColors[1].withValues(alpha: 0.15),
          ],
        ),
      ),
      child: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const SizedBox(height: 24),
              // Animated trophy/icon
              ScaleTransition(
                scale: _scoreScaleAnimation,
                child: RotationTransition(
                  turns: Tween<double>(begin: 0.0, end: 0.05).animate(
                    CurvedAnimation(
                      parent: _scoreAnimationController,
                      curve: Curves.elasticOut,
                    ),
                  ),
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(colors: gradientColors),
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: color.withValues(alpha: 0.3),
                          blurRadius: 12,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                    child: Icon(
                      icon,
                      size: 60,
                      color: theme.colorScheme.onPrimary,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 20),
              // Title with animation
              FadeTransition(
                opacity: _scoreScaleAnimation,
                child: Text(
                  localizations.quizGameQuizComplete,
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: context.textColor,
                  ),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                message,
                style: theme.textTheme.titleMedium?.copyWith(
                  color: context.textSecondaryColor,
                ),
              ),
              if (quizProvider.bestStreakThisRun >= 2) ...[
                const SizedBox(height: 14),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        Colors.orange.shade600,
                        Colors.deepOrange.shade400,
                      ],
                    ),
                    borderRadius: BorderRadius.circular(24),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.orange.withValues(alpha: 0.38),
                        blurRadius: 10,
                      ),
                    ],
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(
                        Icons.local_fire_department_rounded,
                        color: Colors.white,
                        size: 22,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '×${quizProvider.bestStreakThisRun}',
                        style: theme.textTheme.titleMedium?.copyWith(
                          color: Colors.white,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 24),
              // Score card with animation
              ScaleTransition(
                scale: _scoreScaleAnimation,
                child: Container(
                  padding: const EdgeInsets.all(18.0),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        theme.colorScheme.primaryContainer,
                        theme.colorScheme.secondaryContainer,
                      ],
                    ),
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(
                        color: theme.colorScheme.primary.withValues(alpha: 0.2),
                        blurRadius: 8,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                  child: Column(
                    children: [
                      TweenAnimationBuilder<int>(
                        duration: const Duration(milliseconds: 1500),
                        tween: IntTween(begin: 0, end: quizProvider.score),
                        builder: (context, value, child) {
                          return Text(
                            '$value',
                            style: theme.textTheme.headlineMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: theme.colorScheme.onPrimaryContainer,
                            ),
                          );
                        },
                      ),
                      Text(
                        '${localizations.quizGameOutOf} ${quizProvider.totalQuestions}',
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onPrimaryContainer,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surface,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: TweenAnimationBuilder<double>(
                          duration: const Duration(milliseconds: 1500),
                          tween: Tween<double>(
                            begin: 0.0,
                            end: scorePercentage,
                          ),
                          builder: (context, value, child) {
                            return Text(
                              '${value.toStringAsFixed(0)}%',
                              style: theme.textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: context.navyTextColor,
                              ),
                            );
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 24),

              // Detailed statistics card
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: theme.isDarkTheme
                        ? [
                            theme.colorScheme.surfaceContainerHigh.withValues(
                              alpha: 0.98,
                            ),
                            theme.colorScheme.surfaceContainer.withValues(
                              alpha: 0.92,
                            ),
                          ]
                        : [
                            theme.colorScheme.surface.withValues(alpha: 0.98),
                            theme.colorScheme.surface.withValues(alpha: 0.88),
                          ],
                  ),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: theme.isDarkTheme
                        ? theme.colorScheme.outline.withValues(alpha: 0.35)
                        : theme.colorScheme.outline.withValues(alpha: 0.22),
                    width: 1,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: theme.ambientShadow(
                        lightOpacity: 0.06,
                        darkOpacity: 0.38,
                      ),
                      blurRadius: 8,
                      spreadRadius: 0,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                child: Column(
                  children: [
                    Text(
                      localizations.quizGameStatistics,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: context.textColor,
                      ),
                    ),
                    const SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceAround,
                      children: [
                        _buildStatItem(
                          context,
                          theme,
                          localizations.quizGameCorrectAnswers,
                          '${quizProvider.score}',
                          Colors.green,
                          Icons.check_circle_rounded,
                        ),
                        Container(
                          width: 1,
                          height: 40,
                          color: theme.colorScheme.outline.withValues(
                            alpha: 0.3,
                          ),
                        ),
                        _buildStatItem(
                          context,
                          theme,
                          localizations.quizGameIncorrectAnswers,
                          '${quizProvider.totalQuestions - quizProvider.score}',
                          Colors.red,
                          Icons.cancel_rounded,
                        ),
                        Container(
                          width: 1,
                          height: 40,
                          color: theme.colorScheme.outline.withValues(
                            alpha: 0.3,
                          ),
                        ),
                        _buildStatItem(
                          context,
                          theme,
                          localizations.quizGameTotal,
                          '${quizProvider.totalQuestions}',
                          context.navyIconColor,
                          Icons.quiz_rounded,
                        ),
                      ],
                    ),
                  ],
                ),
              ),

              const SizedBox(height: 24),

              // Action buttons (leaderboard only when logged in — API requires JWT)
              Column(
                children: [
                  Selector<AuthProvider, bool>(
                    selector: (_, auth) => auth.isAuthenticated,
                    builder: (context, isAuthenticated, _) {
                      return Row(
                        children: [
                          if (isAuthenticated) ...[
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: () {
                                  Navigator.of(
                                    context,
                                  ).pushNamed(AppRoutes.leaderboard);
                                },
                                icon: const Icon(
                                  Icons.leaderboard_rounded,
                                  size: 18,
                                ),
                                label: Text(
                                  localizations.quizGameViewLeaderboard,
                                  style: const TextStyle(
                                    fontSize: 14,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                                style: OutlinedButton.styleFrom(
                                  padding: const EdgeInsets.symmetric(
                                    vertical: 12,
                                  ),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  side: BorderSide(
                                    width: 1.5,
                                    color: theme.colorScheme.outline,
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                          ],
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () {
                                SystemChrome.setEnabledSystemUIMode(
                                  SystemUiMode.edgeToEdge,
                                );
                                quizProvider.reset();
                                Navigator.of(context).pop();
                              },
                              icon: const Icon(Icons.home_rounded, size: 18),
                              label: Text(
                                localizations.quizGameHome,
                                style: const TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              style: OutlinedButton.styleFrom(
                                padding: const EdgeInsets.symmetric(
                                  vertical: 12,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                side: BorderSide(
                                  width: 1.5,
                                  color: theme.colorScheme.outline,
                                ),
                              ),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        // Reset all animations
                        _scoreAnimationController.reset();
                        _questionAnimationController.reset();
                        _progressAnimationController.reset();
                        _definitionAnimationController.reset();
                        _feedbackAnimationController.reset();
                        _splashAnimationController.reset();

                        setState(() {
                          _showSplash = true;
                          _gameStarted = false;
                          _previousQuestionIndex = -1;
                        });

                        // Reset and restart quiz
                        quizProvider.endQuiz();
                        await Future.delayed(const Duration(milliseconds: 300));
                        await quizProvider.startQuiz();

                        if (mounted) {
                          _splashAnimationController.forward();
                          await Future.delayed(
                            const Duration(milliseconds: 2000),
                          );
                          if (mounted) {
                            setState(() {
                              _showSplash = false;
                              _gameStarted = true;
                            });
                            _progressAnimationController.forward();
                            _scoreAnimationController.forward();
                            _questionAnimationController.forward();
                          }
                        }
                      },
                      icon: const Icon(Icons.refresh_rounded, size: 18),
                      label: Text(
                        localizations.quizGamePlayAgain,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        elevation: 3,
                        shadowColor: theme.colorScheme.primary.withValues(
                          alpha: 0.3,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatItem(
    BuildContext context,
    ThemeData theme,
    String label,
    String value,
    Color color,
    IconData icon,
  ) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.1),
            shape: BoxShape.circle,
            border: Border.all(color: color.withValues(alpha: 0.3), width: 1.5),
          ),
          child: Icon(icon, color: color, size: 22),
        ),
        const SizedBox(height: 8),
        Text(
          value,
          style: theme.textTheme.titleLarge?.copyWith(
            fontWeight: FontWeight.bold,
            color: context.textColor,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: theme.textTheme.bodySmall?.copyWith(
            color: context.textSecondaryColor,
            fontSize: 11,
          ),
        ),
      ],
    );
  }
}

/// Subtle grid + dots for quiz splash (light ink on gradient).
class _SplashPatternPainter extends CustomPainter {
  _SplashPatternPainter({required this.accent});

  final Color accent;

  @override
  void paint(Canvas canvas, Size size) {
    final line = Paint()
      ..color = accent.withValues(alpha: 0.06)
      ..strokeWidth = 1
      ..style = PaintingStyle.stroke;
    const step = 34.0;
    for (double x = 0; x <= size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), line);
    }
    for (double y = 0; y <= size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), line);
    }
    final dot = Paint()
      ..color = accent.withValues(alpha: 0.045)
      ..style = PaintingStyle.fill;
    for (double x = step / 2; x < size.width; x += step) {
      for (double y = step / 2; y < size.height; y += step) {
        canvas.drawCircle(Offset(x, y), 1.2, dot);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _SplashPatternPainter oldDelegate) =>
      oldDelegate.accent != accent;
}

/// Custom painter for background pattern
class _BackgroundPatternPainter extends CustomPainter {
  final ThemeData theme;

  _BackgroundPatternPainter(this.theme);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = theme.colorScheme.primary.withValues(alpha: 0.03)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;

    // Draw diagonal lines pattern
    const spacing = 30.0;

    // Draw lines from top-left to bottom-right
    for (double i = -size.height; i < size.width + size.height; i += spacing) {
      canvas.drawLine(
        Offset(i, 0),
        Offset(i + size.height, size.height),
        paint,
      );
    }

    // Draw lines from top-right to bottom-left
    for (double i = size.width; i > -size.height; i -= spacing) {
      canvas.drawLine(
        Offset(i, 0),
        Offset(i - size.height, size.height),
        paint,
      );
    }

    // Add subtle dots pattern
    final dotPaint = Paint()
      ..color = theme.colorScheme.primary.withValues(alpha: 0.02)
      ..style = PaintingStyle.fill;

    const dotSpacing = 50.0;
    for (double x = 0; x < size.width; x += dotSpacing) {
      for (double y = 0; y < size.height; y += dotSpacing) {
        canvas.drawCircle(Offset(x, y), 1.5, dotPaint);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
