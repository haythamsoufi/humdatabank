import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'dart:math' as math;
import '../../providers/public/quiz_game_provider.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../widgets/app_bar.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../config/routes.dart';

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
    quizProvider.selectAnswer(answer);
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

      final quizProvider = Provider.of<QuizGameProvider>(context, listen: false);
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          // Back button for full screen
          Positioned(
            top: MediaQuery.of(context).padding.top + 8,
            left: 8,
            child: SafeArea(
              child: IconButton(
                icon: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.surface.withOpacity(0.9),
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.2),
                        blurRadius: 8,
                      ),
                    ],
                  ),
                  child: Icon(
                    Icons.arrow_back,
                    color: context.textColor,
                  ),
                ),
                onPressed: () {
                  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
                  Navigator.of(context).pop();
                },
              ),
            ),
          ),

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
              _feedbackAnimationController.status != AnimationStatus.forward &&
              _feedbackAnimationController.status != AnimationStatus.completed) {
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
            return _buildErrorScreen(context, quizProvider, theme, localizations);
          }

          if (quizProvider.isQuizComplete) {
            return _buildQuizComplete(context, quizProvider, theme, localizations);
          }

          if (!quizProvider.isQuizActive || quizProvider.currentIndicator == null) {
            return _buildStartScreen(context, quizProvider, theme, localizations);
          }

          return _buildQuizQuestion(context, quizProvider, theme, localizations);
        },
          ),

          // Splash screen overlay
          if (_showSplash)
            _buildSplashScreen(context, theme, localizations),
        ],
      ),
    );
  }

  Widget _buildSplashScreen(BuildContext context, ThemeData theme, AppLocalizations localizations) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            theme.colorScheme.primary,
            theme.colorScheme.secondary,
            theme.colorScheme.tertiary,
          ],
        ),
      ),
      child: FadeTransition(
        opacity: _splashFadeAnimation,
        child: ScaleTransition(
          scale: _splashScaleAnimation,
          child: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.3),
                        blurRadius: 20,
                        spreadRadius: 3,
                      ),
                    ],
                  ),
                  child: Icon(
                    Icons.quiz,
                    size: 60,
                    color: theme.colorScheme.primary,
                  ),
                ),
                const SizedBox(height: 24),
                Text(
                  localizations.quizGameTitle,
                  style: theme.textTheme.headlineLarge?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.bold,
                    shadows: [
                      Shadow(
                        color: Colors.black.withOpacity(0.3),
                        blurRadius: 10,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  localizations.quizGameTestYourKnowledge,
                  style: theme.textTheme.titleMedium?.copyWith(
                    color: Colors.white.withOpacity(0.9),
                    shadows: [
                      Shadow(
                        color: Colors.black.withOpacity(0.2),
                        blurRadius: 8,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 48),
                // Action buttons
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // Leaderboard button
                    ElevatedButton.icon(
                      onPressed: () {
                        Navigator.of(context).pushNamed(AppRoutes.leaderboard);
                      },
                      icon: const Icon(Icons.leaderboard_rounded, size: 20),
                      label: Text(
                        localizations.quizGameViewLeaderboard,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 20,
                          vertical: 14,
                        ),
                        backgroundColor: Colors.white.withOpacity(0.2),
                        foregroundColor: Colors.white,
                        side: const BorderSide(
                          color: Colors.white,
                          width: 1.5,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        elevation: 4,
                        shadowColor: Colors.black.withOpacity(0.3),
                      ),
                    ),
                    const SizedBox(width: 16),
                    // Start button
                    ElevatedButton.icon(
                      onPressed: _startGame,
                      icon: const Icon(Icons.play_arrow_rounded, size: 24),
                      label: Text(
                        localizations.quizGameStartQuiz,
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 24,
                          vertical: 16,
                        ),
                        backgroundColor: Colors.white,
                        foregroundColor: theme.colorScheme.primary,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        elevation: 6,
                        shadowColor: Colors.black.withOpacity(0.4),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLoadingScreen(BuildContext context, ThemeData theme, AppLocalizations localizations) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          CircularProgressIndicator(
            valueColor: AlwaysStoppedAnimation<Color>(
              theme.colorScheme.primary,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            localizations.quizGameLoading,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: context.textSecondaryColor,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildErrorScreen(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
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
              quizProvider.error!,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: theme.colorScheme.error,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: () => quizProvider.startQuiz(),
              child: Text(localizations.quizGameTryAgain),
            ),
          ],
        ),
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

  Widget _buildQuizQuestion(
    BuildContext context,
    QuizGameProvider quizProvider,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    final indicator = quizProvider.currentIndicator!;
    final currentQuestion = quizProvider.questions[quizProvider.currentQuestionIndex];
    final questionText = currentQuestion.questionType == QuizQuestionType.sector
        ? localizations.quizGameWhichSector
        : localizations.quizGameWhichSubsector;

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [
            theme.scaffoldBackgroundColor,
            theme.scaffoldBackgroundColor.withOpacity(0.95),
            theme.colorScheme.primaryContainer.withOpacity(0.1),
          ],
          stops: const [0.0, 0.5, 1.0],
        ),
      ),
      child: CustomPaint(
        painter: _BackgroundPatternPainter(theme),
        child: SafeArea(
          child: Column(
            children: [
              // Modern progress bar with animation
            AnimatedBuilder(
              animation: _progressAnimation,
              builder: (context, child) {
                return Container(
                  height: 6,
                  margin: const EdgeInsets.only(bottom: 8),
                  child: Stack(
                    children: [
                      Container(
                        color: context.lightSurfaceColor,
                      ),
                      FractionallySizedBox(
                        widthFactor: quizProvider.progress * _progressAnimation.value,
                        child: Container(
                          decoration: BoxDecoration(
                            color: theme.colorScheme.primary,
                            borderRadius: BorderRadius.circular(3),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),

            // Question number and score with modern design
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      // Back button
                      IconButton(
                        icon: Icon(
                          Icons.arrow_back_ios_new,
                          size: 18,
                          color: context.textColor,
                        ),
                        onPressed: () {
                          Navigator.of(context).pop();
                        },
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                        tooltip: 'Go back',
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surface.withOpacity(0.8),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: theme.colorScheme.outline.withOpacity(0.2),
                            width: 1,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withOpacity(0.03),
                              blurRadius: 4,
                              offset: const Offset(0, 1),
                            ),
                          ],
                        ),
                        child: Text(
                          'Q${quizProvider.currentQuestionIndex + 1}/${quizProvider.totalQuestions}',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: context.textColor,
                          ),
                        ),
                      ),
                    ],
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: theme.colorScheme.outline.withOpacity(0.2),
                        width: 1,
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          Icons.star,
                          color: Colors.amber.shade600,
                          size: 16,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          '${quizProvider.score}',
                          style: theme.textTheme.bodyLarge?.copyWith(
                            color: context.textColor,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // Main content with slide animation
            Expanded(
              child: quizProvider.questions.isEmpty || quizProvider.currentIndicator == null
                  ? Center(
                      child: CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(
                          theme.colorScheme.primary,
                        ),
                      ),
                    )
                  : SlideTransition(
                      position: Tween<Offset>(
                        begin: const Offset(0.3, 0.0),
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
                          padding: const EdgeInsets.all(20.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                        // Question text without box
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 8.0),
                          child: Text(
                            questionText,
                            style: theme.textTheme.titleLarge?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: context.textColor,
                              height: 1.3,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ),

                        const SizedBox(height: 16),

                        // Indicator card with modern design
                        Container(
                          padding: const EdgeInsets.all(12.0),
                          decoration: BoxDecoration(
                            color: theme.cardColor,
                            borderRadius: BorderRadius.circular(8),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withOpacity(0.05),
                                blurRadius: 8,
                                offset: const Offset(0, 2),
                              ),
                            ],
                            border: Border.all(
                              color: theme.colorScheme.outline.withOpacity(0.1),
                              width: 1,
                            ),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                indicator.displayName,
                                style: theme.textTheme.titleMedium?.copyWith(
                                  fontWeight: FontWeight.bold,
                                  color: context.textColor,
                                ),
                              ),
                              // Definition - only shown after answer selection
                              if (quizProvider.showResult) ...[
                                const SizedBox(height: 12),
                                FadeTransition(
                                  opacity: _definitionFadeAnimation,
                                  child: Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      color: theme.colorScheme.surfaceContainerHighest,
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          children: [
                                            Icon(
                                              Icons.info_outline,
                                              size: 16,
                                              color: theme.colorScheme.primary,
                                            ),
                                            const SizedBox(width: 6),
                                            Text(
                                              localizations.quizGameDefinition,
                                              style: theme.textTheme.bodyMedium?.copyWith(
                                                fontWeight: FontWeight.bold,
                                                color: theme.colorScheme.primary,
                                              ),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          indicator.localizedDefinition ??
                                          indicator.definition ??
                                          localizations.quizGameNoDefinition,
                                          style: theme.textTheme.bodyMedium?.copyWith(
                                            color: context.textSecondaryColor,
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

                        const SizedBox(height: 16),

                        // Answer options with animations
                        ...quizProvider.options.asMap().entries.map((entry) {
                          final index = entry.key;
                          final option = entry.value;
                          return TweenAnimationBuilder<double>(
                            duration: Duration(milliseconds: 300 + (index * 100)),
                            tween: Tween<double>(begin: 0.0, end: 1.0),
                            curve: Curves.easeOut,
                            builder: (context, value, child) {
                              return Transform.translate(
                                offset: Offset(0, 20 * (1 - value)),
                                child: Opacity(
                                  opacity: value,
                                  child: child,
                                ),
                              );
                            },
                            child: _buildOptionButton(
                              context,
                              option,
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

            // Navigation buttons with feedback
            if (quizProvider.showResult)
              _buildResultFeedback(context, quizProvider, theme, localizations),
          ],
          ),
        ),
      ),
    );
  }

  Widget _buildOptionButton(
    BuildContext context,
    String option,
    QuizGameProvider quizProvider,
    ThemeData theme,
  ) {
    final isSelected = quizProvider.selectedAnswer == option;
    final showResult = quizProvider.showResult;
    final isCorrect = option == quizProvider.correctAnswer;
    final isWrong = isSelected && !isCorrect;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8.0),
      child: TweenAnimationBuilder<double>(
        duration: const Duration(milliseconds: 200),
        tween: Tween<double>(
          begin: 1.0,
          end: isSelected ? 1.02 : 1.0,
        ),
        builder: (context, scale, child) {
          return Transform.scale(
            scale: scale,
            child: GestureDetector(
              onTap: showResult ? null : () => _handleAnswerSelection(quizProvider, option),
              child: AnimatedContainer(
                 duration: const Duration(milliseconds: 300),
                 curve: Curves.easeOut,
                 padding: const EdgeInsets.all(12.0),
                 decoration: BoxDecoration(
                   color: _getOptionColor(context, theme, showResult, isCorrect, isWrong, isSelected),
                   borderRadius: BorderRadius.circular(8),
                   border: Border.all(
                     color: _getOptionBorderColor(theme, showResult, isCorrect, isWrong, isSelected),
                     width: 1.5,
                   ),
                   boxShadow: [
                     BoxShadow(
                       color: _getOptionShadowColor(theme, showResult, isCorrect, isWrong, isSelected),
                       blurRadius: isSelected ? 6 : 3,
                       spreadRadius: isSelected ? 1 : 0,
                       offset: Offset(0, isSelected ? 2 : 1),
                     ),
                   ],
                 ),
                child: Row(
                  children: [
                    Container(
                      width: 32,
                      height: 32,
                      decoration: BoxDecoration(
                        color: _getOptionIconBackgroundColor(
                          theme,
                          showResult,
                          isCorrect,
                          isWrong,
                          isSelected,
                        ),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        _getOptionIcon(showResult, isCorrect, isWrong, isSelected),
                        color: _getOptionIconColor(theme, showResult, isCorrect, isWrong, isSelected),
                        size: 20,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        option,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: _getOptionTextColor(context, theme, showResult, isCorrect, isWrong, isSelected),
                          fontWeight: isSelected || (showResult && isCorrect)
                              ? FontWeight.bold
                              : FontWeight.w500,
                          fontSize: 14,
                        ),
                      ),
                    ),
                    if (showResult && isCorrect)
                      ScaleTransition(
                        scale: _feedbackScaleAnimation,
                        child: Icon(
                          Icons.check_circle,
                          color: Colors.green.shade600,
                          size: 22,
                        ),
                      ),
                    if (showResult && isWrong)
                      ScaleTransition(
                        scale: _feedbackScaleAnimation,
                        child: Icon(
                          Icons.cancel,
                          color: Colors.red.shade600,
                          size: 22,
                        ),
                      ),
                  ],
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
        return Colors.green.shade50;
      } else if (isWrong) {
        return Colors.red.shade50;
      } else {
        return context.cardColor.withOpacity(0.5);
      }
    } else {
      return isSelected
          ? theme.colorScheme.primaryContainer.withOpacity(0.7)
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
        return Colors.green.shade600;
      } else if (isWrong) {
        return Colors.red.shade600;
      } else {
        return Colors.transparent;
      }
    } else {
      return isSelected
          ? theme.colorScheme.primary
          : theme.colorScheme.outline.withOpacity(0.2);
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
        return Colors.green.withOpacity(0.3);
      } else if (isWrong) {
        return Colors.red.withOpacity(0.3);
      }
    } else if (isSelected) {
      return theme.colorScheme.primary.withOpacity(0.4);
    }
    return Colors.black.withOpacity(0.1);
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
        return Colors.green.shade100;
      } else if (isWrong) {
        return Colors.red.shade100;
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
        return Colors.green.shade700;
      } else if (isWrong) {
        return Colors.red.shade700;
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
        return Colors.green.shade900;
      } else if (isWrong) {
        return Colors.red.shade900;
      } else {
        return context.textColor.withOpacity(0.5);
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
    return Container(
      padding: const EdgeInsets.all(12.0),
      decoration: BoxDecoration(
        color: context.cardColor,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 8,
            offset: const Offset(0, -2),
          ),
        ],
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(16),
        ),
      ),
      child: SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Feedback message with animation - styled as a badge/status indicator
            ScaleTransition(
              scale: _feedbackScaleAnimation,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: quizProvider.isCorrect
                      ? Colors.green.shade50
                      : Colors.red.shade50,
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(
                    color: quizProvider.isCorrect
                        ? Colors.green.shade300
                        : Colors.red.shade300,
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
                            ? Colors.green.shade600
                            : Colors.red.shade600,
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        quizProvider.isCorrect
                            ? Icons.check_rounded
                            : Icons.close_rounded,
                        color: Colors.white,
                        size: 14,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      quizProvider.isCorrect ? localizations.quizGameCorrect : localizations.quizGameIncorrect,
                      style: theme.textTheme.bodyLarge?.copyWith(
                        color: quizProvider.isCorrect
                            ? Colors.green.shade900
                            : Colors.red.shade900,
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
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        elevation: 2,
                      ),
                      child: Text(
                        localizations.quizGameNextQuestion,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.bold,
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
                            color: theme.colorScheme.primary.withOpacity(0.4),
                            blurRadius: 12,
                            spreadRadius: 2,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: ElevatedButton(
                        onPressed: () {
                          // Navigate to results screen
                          quizProvider.nextQuestion(); // This will mark quiz as complete
                        },
                        style: ElevatedButton.styleFrom(
                          padding: const EdgeInsets.symmetric(vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
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
                              style: const TextStyle(
                                fontSize: 14,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                            const SizedBox(width: 6),
                            const Icon(
                              Icons.arrow_forward_rounded,
                              size: 18,
                              color: Colors.white,
                            ),
                          ],
                        ),
                      ),
                    ),
            ),
          ],
        ),
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
            gradientColors[0].withOpacity(0.1),
            gradientColors[1].withOpacity(0.15),
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
                      gradient: LinearGradient(
                        colors: gradientColors,
                      ),
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: color.withOpacity(0.3),
                          blurRadius: 12,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                    child: Icon(
                      icon,
                      size: 60,
                      color: Colors.white,
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
                        color: theme.colorScheme.primary.withOpacity(0.2),
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
                          tween: Tween<double>(begin: 0.0, end: scorePercentage),
                          builder: (context, value, child) {
                            return Text(
                              '${value.toStringAsFixed(0)}%',
                              style: theme.textTheme.titleLarge?.copyWith(
                                fontWeight: FontWeight.bold,
                                color: theme.colorScheme.primary,
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
                     colors: [
                       Colors.white.withOpacity(0.95),
                       Colors.white.withOpacity(0.85),
                     ],
                   ),
                   borderRadius: BorderRadius.circular(12),
                   border: Border.all(
                     color: Colors.white.withOpacity(0.5),
                     width: 1,
                   ),
                   boxShadow: [
                     BoxShadow(
                       color: Colors.black.withOpacity(0.05),
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
                           color: theme.colorScheme.outline.withOpacity(0.3),
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
                           color: theme.colorScheme.outline.withOpacity(0.3),
                         ),
                         _buildStatItem(
                           context,
                           theme,
                           localizations.quizGameTotal,
                           '${quizProvider.totalQuestions}',
                           theme.colorScheme.primary,
                           Icons.quiz_rounded,
                         ),
                       ],
                     ),
                   ],
                 ),
               ),

               const SizedBox(height: 24),

               // Action buttons
               Column(
                 children: [
                   Row(
                     children: [
                       Expanded(
                         child: OutlinedButton.icon(
                           onPressed: () {
                             Navigator.of(context).pushNamed(AppRoutes.leaderboard);
                           },
                           icon: const Icon(Icons.leaderboard_rounded, size: 18),
                           label: Text(
                             localizations.quizGameViewLeaderboard,
                             style: const TextStyle(
                               fontSize: 14,
                               fontWeight: FontWeight.bold,
                             ),
                           ),
                           style: OutlinedButton.styleFrom(
                             padding: const EdgeInsets.symmetric(vertical: 12),
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
                       Expanded(
                         child: OutlinedButton.icon(
                           onPressed: () {
                             SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
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
                             padding: const EdgeInsets.symmetric(vertical: 12),
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
                           await Future.delayed(const Duration(milliseconds: 2000));
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
                         shadowColor: theme.colorScheme.primary.withOpacity(0.3),
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
            color: color.withOpacity(0.1),
            shape: BoxShape.circle,
            border: Border.all(
              color: color.withOpacity(0.3),
              width: 1.5,
            ),
          ),
          child: Icon(
            icon,
            color: color,
            size: 22,
          ),
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

/// Custom painter for background pattern
class _BackgroundPatternPainter extends CustomPainter {
  final ThemeData theme;

  _BackgroundPatternPainter(this.theme);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = theme.colorScheme.primary.withOpacity(0.03)
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
      ..color = theme.colorScheme.primary.withOpacity(0.02)
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
