import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/providers/shared/ai_chat_provider.dart';

void main() {
  group('AiChatProvider.isUnclassifiedStreamError', () {
    test('treats the backend catch-all and missing types as retryable', () {
      expect(AiChatProvider.isUnclassifiedStreamError('Error'), isTrue);
      expect(AiChatProvider.isUnclassifiedStreamError(null), isTrue);
      expect(AiChatProvider.isUnclassifiedStreamError(' '), isTrue);
    });

    test('done prefers the server HTML and keeps narration above it', () {
      expect(
        AiChatProvider.composeDoneContent(
          buffer: "I'll look this up\n\n<p>partial",
          response: '<p>Full answer</p>',
          narration: "I'll look this up",
        ),
        "I'll look this up\n\n<p>Full answer</p>",
      );
    });

    test('done does not duplicate narration the server already included', () {
      const response = "I'll look this up\n\n<p>Full</p>";
      expect(
        AiChatProvider.composeDoneContent(
          buffer: 'hello',
          response: response,
          narration: "I'll look this up",
        ),
        response,
      );
    });

    test('persisted assistant text matches the server body, not the narration prefix', () {
      expect(
        AiChatProvider.persistedAssistantContent(
          response: '<p>Full answer</p>',
          structured: const [],
        ),
        '<p>Full answer</p>',
      );
      expect(
        AiChatProvider.persistedAssistantContent(
          response: '',
          structured: const [
            {'type': 'worldmap'},
          ],
        ),
        '[Map visualization]',
      );
    });

    test('a finished turn keeps an existing title', () {
      expect(
        AiChatProvider.titleAfterTurn(
          existingTitle: 'Volunteers in Kenya',
          fallback: 'raw prompt that should not replace it',
        ),
        'Volunteers in Kenya',
      );
      expect(
        AiChatProvider.titleAfterTurn(existingTitle: '  ', fallback: 'A' * 90),
        '${'A' * 80}...',
      );
    });

    test('localized progress lines that end with an ellipsis count as in-flight status', () {
      expect(AiChatProvider.isPipelineProgressDetail('Chargement des pays…'), isTrue);
      expect(AiChatProvider.isPipelineProgressDetail('Loading countries...'), isTrue);
      expect(AiChatProvider.isPipelineProgressDetail('Selected indicator: Volunteers'), isFalse);
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
