import '../indicator_bank/indicator.dart';

/// Quiz question model
class QuizQuestion {
  final Indicator indicator;
  final QuizQuestionType questionType;
  final String correctAnswer;
  final List<String> options;

  QuizQuestion({
    required this.indicator,
    required this.questionType,
    required this.correctAnswer,
    required this.options,
  });
}

/// Question type enum
enum QuizQuestionType {
  sector,
  subsector,
}
