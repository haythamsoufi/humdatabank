import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/providers/shared/ai_chat_provider.dart';

void main() {
  group('AiChatProvider.isUnclassifiedStreamError', () {
    test('treats the backend catch-all and missing types as retryable', () {
      expect(AiChatProvider.isUnclassifiedStreamError('Error'), isTrue);
      expect(AiChatProvider.isUnclassifiedStreamError(null), isTrue);
      expect(AiChatProvider.isUnclassifiedStreamError(' '), isTrue);
    });

    test('keeps classified errors visible to the user', () {
      for (final t in [
        'quota_exceeded',
        'budget_exceeded',
        'dlp_blocked',
        'dlp_requires_confirmation',
        'auth_required',
        'stream_idle_timeout',
      ]) {
        expect(AiChatProvider.isUnclassifiedStreamError(t), isFalse, reason: t);
      }
    });
  });
}
