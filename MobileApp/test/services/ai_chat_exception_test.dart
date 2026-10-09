import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/ai_chat.dart';
import 'package:hum_databank_app/services/ai_chat_exception.dart';

void main() {
  group('AiChatHttpException.fromResponse', () {
    test('keeps backend message and maps 403 to forbidden', () {
      final e = AiChatHttpException.fromResponse(
        403,
        '{"success":false,"message":"AI beta access is limited to selected users."}',
      );
      expect(e.message, 'AI beta access is limited to selected users.');
      expect(e.chatErrorType, 'forbidden');
    });

    test('maps 401 to auth_required', () {
      final e = AiChatHttpException.fromResponse(401, '{"message":"Auth required"}');
      expect(e.chatErrorType, 'auth_required');
    });

    test('maps 429 and quota error_type to quota_exceeded', () {
      expect(AiChatHttpException.fromResponse(429, '{}').chatErrorType, 'quota_exceeded');
      expect(
        AiChatHttpException.fromResponse(500, '{"error_type":"quota_exceeded"}').chatErrorType,
        'quota_exceeded',
      );
    });

    test('tolerates non-JSON bodies (proxy HTML error page)', () {
      final e = AiChatHttpException.fromResponse(502, '<html>Bad Gateway</html>');
      expect(e.chatErrorType, 'service_unavailable');
      expect(e.message, contains('temporarily unavailable'));
    });

    test('plain 500 stays server_error and skips the "Chat failed" placeholder', () {
      final e = AiChatHttpException.fromResponse(
        500,
        '{"error":"Chat failed","error_type":"OperationalError","message":"An internal error occurred."}',
      );
      expect(e.chatErrorType, 'server_error');
      expect(e.backendErrorType, 'OperationalError');
      expect(e.message, 'An internal error occurred.');
    });
  });

  group('removeTrailingFailedAttempt', () {
    test('removes every trailing error bubble and placeholder, keeps the user turn', () {
      final messages = [
        AiChatMessage(role: 'user', content: 'Volunteers in Syria over time'),
        AiChatMessage(role: 'error', content: 'x', errorType: 'server_error'),
        AiChatMessage(role: 'error', content: 'x', errorType: 'server_error'),
        AiChatMessage(role: 'assistant', content: ''),
      ];
      removeTrailingFailedAttempt(messages);
      expect(messages.map((m) => m.role).toList(), ['user']);
    });

    test('leaves a real assistant reply alone', () {
      final messages = [
        AiChatMessage(role: 'user', content: 'hi'),
        AiChatMessage(role: 'assistant', content: 'hello'),
      ];
      removeTrailingFailedAttempt(messages);
      expect(messages.length, 2);
    });
  });
}
