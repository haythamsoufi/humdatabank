import 'package:flutter/foundation.dart';
import 'dart:math';
import '../../models/indicator_bank/indicator.dart';
import '../../models/public/quiz_question.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../di/service_locator.dart';

/// Quiz game provider that manages quiz state and logic
class QuizGameProvider with ChangeNotifier {
  IndicatorBankProvider _indicatorBankProvider;
  LanguageProvider? _languageProvider;
  final ApiService _apiService = sl<ApiService>();

  // Quiz state
  bool _isQuizActive = false;
  bool _isLoading = false;
  String? _error;
  int _currentQuestionIndex = 0;
  int _score = 0;
  int _totalQuestions = 10;
  int _answerStreak = 0;
  int _bestStreak = 0;

  // Current question data
  Indicator? _currentIndicator;
  List<String> _options = [];
  String? _correctAnswer;
  String? _selectedAnswer;
  bool _showResult = false;
  bool _isCorrect = false;

  // Quiz questions
  List<QuizQuestion> _questions = [];

  QuizGameProvider(this._indicatorBankProvider);

  void updateIndicatorBankProvider(IndicatorBankProvider provider) {
    if (_indicatorBankProvider != provider) {
      _indicatorBankProvider = provider;
      notifyListeners();
    }
  }

  void updateLanguageProvider(LanguageProvider? provider) {
    if (_languageProvider != provider) {
      _languageProvider = provider;
      notifyListeners();
    }
  }

  // Getters
  bool get isQuizActive => _isQuizActive;
  bool get isLoading => _isLoading;
  String? get error => _error;
  int get currentQuestionIndex => _currentQuestionIndex;
  int get score => _score;
  int get totalQuestions => _totalQuestions;
  Indicator? get currentIndicator => _currentIndicator;
  List<String> get options => _options;
  String? get selectedAnswer => _selectedAnswer;
  String? get correctAnswer => _correctAnswer;
  bool get showResult => _showResult;
  bool get isCorrect => _isCorrect;
  List<QuizQuestion> get questions => _questions;
  int get answerStreak => _answerStreak;
  int get bestStreakThisRun => _bestStreak;

  bool get hasMoreQuestions => _currentQuestionIndex < _questions.length - 1;
  bool get isQuizComplete => _currentQuestionIndex >= _questions.length;
  double get progress => _questions.isEmpty
      ? 0.0
      : (_currentQuestionIndex + 1) / _questions.length;
  double get scorePercentage =>
      _questions.isEmpty ? 0.0 : (_score / _questions.length) * 100;

  /// Start a new quiz game
  Future<void> startQuiz({int numQuestions = 10}) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      // Get current locale from language provider
      final locale = _languageProvider?.currentLanguage ?? 'en';

      // Ensure indicator bank data is loaded with correct locale
      if (_indicatorBankProvider.allIndicators.isEmpty) {
        await _indicatorBankProvider.loadData(locale: locale);
      } else {
        // Reload data if locale has changed
        await _indicatorBankProvider.loadData(locale: locale);
      }

      // Filter indicators that have sectors or subsectors
      final validIndicators = _indicatorBankProvider.allIndicators
          .where(
            (ind) =>
                (ind.sector != null && ind.displaySector.isNotEmpty) ||
                (ind.subSector != null && ind.displaySubSector.isNotEmpty),
          )
          .toList();

      if (validIndicators.isEmpty) {
        _error = 'No indicators with sectors or subsectors available for quiz';
        _isLoading = false;
        notifyListeners();
        return;
      }

      // Generate questions
      _questions = _generateQuestions(validIndicators, numQuestions);

      _totalQuestions = _questions.length;
      _currentQuestionIndex = 0;
      _score = 0;
      _answerStreak = 0;
      _bestStreak = 0;
      _isQuizActive = true;
      _loadCurrentQuestion();
    } catch (e) {
      _error = 'Failed to start quiz: $e';
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Generate quiz questions
  List<QuizQuestion> _generateQuestions(
    List<Indicator> indicators,
    int numQuestions,
  ) {
    final questions = <QuizQuestion>[];
    final random = Random();
    final usedIndicators = <int>{};

    // Get all unique sectors and subsectors for creating wrong answers
    final allSectors = <String>{};
    final allSubSectors = <String>{};

    for (final indicator in indicators) {
      if (indicator.displaySector.isNotEmpty) {
        allSectors.add(indicator.displaySector);
      }
      if (indicator.displaySubSector.isNotEmpty) {
        allSubSectors.add(indicator.displaySubSector);
      }
    }

    while (questions.length < numQuestions &&
        usedIndicators.length < indicators.length) {
      // Pick a random indicator we haven't used yet
      Indicator? indicator;
      int attempts = 0;
      while (indicator == null && attempts < 100) {
        final randomIndex = random.nextInt(indicators.length);
        if (!usedIndicators.contains(randomIndex)) {
          indicator = indicators[randomIndex];
          usedIndicators.add(randomIndex);
        }
        attempts++;
      }

      if (indicator == null) break;

      // Determine question type: sector or subsector
      final hasSector = indicator.displaySector.isNotEmpty;
      final hasSubSector = indicator.displaySubSector.isNotEmpty;

      QuizQuestionType? questionType;
      String? correctAnswer;

      if (hasSector && hasSubSector) {
        // Randomly choose between sector and subsector
        questionType = random.nextBool()
            ? QuizQuestionType.sector
            : QuizQuestionType.subsector;
        correctAnswer = questionType == QuizQuestionType.sector
            ? indicator.displaySector
            : indicator.displaySubSector;
      } else if (hasSector) {
        questionType = QuizQuestionType.sector;
        correctAnswer = indicator.displaySector;
      } else if (hasSubSector) {
        questionType = QuizQuestionType.subsector;
        correctAnswer = indicator.displaySubSector;
      }

      if (questionType == null ||
          correctAnswer == null ||
          correctAnswer.isEmpty) {
        continue;
      }

      // Generate wrong answers
      final wrongAnswers = questionType == QuizQuestionType.sector
          ? _generateWrongAnswers(correctAnswer, allSectors.toList(), 3)
          : _generateWrongAnswers(correctAnswer, allSubSectors.toList(), 3);

      // Create options with correct answer and wrong answers
      final options = [correctAnswer, ...wrongAnswers];
      options.shuffle(random);

      questions.add(
        QuizQuestion(
          indicator: indicator,
          questionType: questionType,
          correctAnswer: correctAnswer,
          options: options,
        ),
      );
    }

    return questions;
  }

  /// Generate wrong answers from available options
  List<String> _generateWrongAnswers(
    String correctAnswer,
    List<String> allAnswers,
    int count,
  ) {
    final random = Random();
    final wrongAnswers = <String>{};
    final availableAnswers = allAnswers
        .where((a) => a != correctAnswer)
        .toList();

    while (wrongAnswers.length < count &&
        wrongAnswers.length < availableAnswers.length) {
      final randomAnswer =
          availableAnswers[random.nextInt(availableAnswers.length)];
      wrongAnswers.add(randomAnswer);
    }

    return wrongAnswers.toList();
  }

  /// Load the current question
  void _loadCurrentQuestion() {
    if (_questions.isEmpty || _currentQuestionIndex >= _questions.length) {
      return;
    }

    final question = _questions[_currentQuestionIndex];
    _currentIndicator = question.indicator;
    _options = List<String>.from(question.options);
    _correctAnswer = question.correctAnswer;
    _selectedAnswer = null;
    _showResult = false;
    _isLoading = false;
    notifyListeners();
  }

  /// Select an answer
  void selectAnswer(String answer) {
    if (_showResult) return; // Already answered

    _selectedAnswer = answer;
    _isCorrect = answer == _correctAnswer;
    _showResult = true;

    if (_isCorrect) {
      _score++;
      _answerStreak++;
      if (_answerStreak > _bestStreak) {
        _bestStreak = _answerStreak;
      }
    } else {
      _answerStreak = 0;
    }

    notifyListeners();
  }

  /// Move to next question
  void nextQuestion() {
    if (!hasMoreQuestions) {
      // Mark quiz as complete when no more questions
      _currentQuestionIndex = _questions.length; // Set to beyond last question
      _showResult = false; // Reset result state

      // Submit score to backend if user is authenticated
      _submitScore();

      notifyListeners();
      return;
    }

    _currentQuestionIndex++;
    _loadCurrentQuestion();
  }

  /// Submit quiz score to backend
  Future<void> _submitScore() async {
    if (_score <= 0) return; // Don't submit zero scores

    try {
      final response = await _apiService.post(
        AppConfig.mobileQuizSubmitScoreEndpoint,
        body: {'score': _score},
        includeAuth: true,
      );

      if (response.statusCode == 200) {
        DebugLogger.logInfo(
          'QUIZ',
          'Score submitted successfully: $_score points',
        );
      } else {
        DebugLogger.logWarn(
          'QUIZ',
          'Failed to submit score: ${response.statusCode}',
        );
      }
    } catch (e) {
      // Silently fail - score submission is not critical
      DebugLogger.logWarn('QUIZ', 'Error submitting score: $e');
    }
  }

  /// Restart the quiz
  Future<void> restartQuiz() async {
    await startQuiz(numQuestions: _totalQuestions);
  }

  /// End the quiz
  void endQuiz() {
    _isQuizActive = false;
    _currentQuestionIndex = 0;
    _questions.clear();
    _currentIndicator = null;
    _options.clear();
    _correctAnswer = null;
    _selectedAnswer = null;
    _showResult = false;
    _answerStreak = 0;
    _bestStreak = 0;
    notifyListeners();
  }

  /// Reset quiz state
  void reset() {
    _isQuizActive = false;
    _currentQuestionIndex = 0;
    _score = 0;
    _questions.clear();
    _currentIndicator = null;
    _options.clear();
    _correctAnswer = null;
    _selectedAnswer = null;
    _showResult = false;
    _isCorrect = false;
    _error = null;
    _isLoading = false;
    _answerStreak = 0;
    _bestStreak = 0;
    notifyListeners();
  }
}
