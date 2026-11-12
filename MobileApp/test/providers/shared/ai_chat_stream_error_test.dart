import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/ai_chat.dart';
import 'package:hum_databank_app/providers/shared/ai_chat_provider.dart';
import 'package:hum_databank_app/services/ai_chat_service.dart';

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

  group('mergeAgentSteps', () {
    test('a later snapshot does not replace steps already on screen', () {
      const preparing = AiChatAgentStep(message: 'Preparing query…');
      const searching = AiChatAgentStep(message: 'Searching documents');
      expect(
        AiChatProvider.mergeAgentSteps(const [preparing, searching], const [preparing]),
        [preparing, searching],
      );
      expect(
        AiChatProvider.mergeAgentSteps(const [preparing], const [preparing, searching]),
        [preparing, searching],
      );
      expect(AiChatProvider.mergeAgentSteps(const [preparing], const []), [preparing]);
    });
  });

  group('streamRequestMayBeOnServer', () {
    test('a header timeout means the request may already be running', () {
      expect(
        streamRequestMayBeOnServer(
          TimeoutException('Future not completed'),
          handedToNetwork: true,
        ),
        isTrue,
      );
    });

    test('connection refused never reached the server', () {
      expect(
        streamRequestMayBeOnServer(
          Exception('SocketException: Connection refused'),
          handedToNetwork: true,
        ),
        isFalse,
      );
    });

    test('a request that never left the device was not submitted', () {
      expect(
        streamRequestMayBeOnServer(
          TimeoutException('Future not completed'),
          handedToNetwork: false,
        ),
        isFalse,
      );
    });
  });
}
