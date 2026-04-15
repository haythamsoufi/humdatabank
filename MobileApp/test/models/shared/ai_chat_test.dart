import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/ai_chat.dart';

void main() {
  group('AiChatAgentStep', () {
    test('constructs with required fields and default detailLines', () {
      const step = AiChatAgentStep(message: 'Searching...');

      expect(step.message, 'Searching...');
      expect(step.detailLines, isEmpty);
    });

    test('constructs with explicit detailLines', () {
      const step = AiChatAgentStep(
        message: 'Querying DB',
        detailLines: ['table: users', 'limit: 10'],
      );

      expect(step.message, 'Querying DB');
      expect(step.detailLines, ['table: users', 'limit: 10']);
    });

    test('copyWith overrides message only', () {
      const step = AiChatAgentStep(
        message: 'Original',
        detailLines: ['line1'],
      );
      final copy = step.copyWith(message: 'Updated');

      expect(copy.message, 'Updated');
      expect(copy.detailLines, ['line1']);
    });

    test('copyWith overrides detailLines only', () {
      const step = AiChatAgentStep(message: 'Msg');
      final copy = step.copyWith(detailLines: ['a', 'b']);

      expect(copy.message, 'Msg');
      expect(copy.detailLines, ['a', 'b']);
    });

    test('copyWith with no args returns equivalent copy', () {
      const step = AiChatAgentStep(
        message: 'Keep',
        detailLines: ['x'],
      );
      final copy = step.copyWith();

      expect(copy.message, step.message);
      expect(copy.detailLines, step.detailLines);
    });
  });

  group('AiChatMessage', () {
    test('constructs with required fields and defaults', () {
      final msg = AiChatMessage(role: 'user', content: 'Hello');

      expect(msg.role, 'user');
      expect(msg.content, 'Hello');
      expect(msg.createdAt, isNotNull);
      expect(msg.errorType, isNull);
      expect(msg.retryDelay, isNull);
      expect(msg.traceId, isNull);
      expect(msg.userRating, isNull);
      expect(msg.structuredPayloads, isEmpty);
      expect(msg.confidence, isNull);
      expect(msg.groundingScore, isNull);
    });

    test('constructs with all optional fields', () {
      final now = DateTime.utc(2025, 6, 1);
      final msg = AiChatMessage(
        role: 'assistant',
        content: 'Response',
        createdAt: now,
        errorType: 'server_error',
        retryDelay: 5.0,
        traceId: 123,
        userRating: 'like',
        structuredPayloads: [
          {'type': 'chart'}
        ],
        confidence: 0.95,
        groundingScore: 0.8,
      );

      expect(msg.role, 'assistant');
      expect(msg.content, 'Response');
      expect(msg.createdAt, now);
      expect(msg.errorType, 'server_error');
      expect(msg.retryDelay, 5.0);
      expect(msg.traceId, 123);
      expect(msg.userRating, 'like');
      expect(msg.structuredPayloads, hasLength(1));
      expect(msg.confidence, 0.95);
      expect(msg.groundingScore, 0.8);
    });

    test('copyWith overrides specified fields', () {
      final msg = AiChatMessage(
        role: 'user',
        content: 'Hi',
        traceId: 10,
        userRating: 'dislike',
      );
      final copy = msg.copyWith(content: 'Updated', userRating: 'like');

      expect(copy.content, 'Updated');
      expect(copy.userRating, 'like');
      expect(copy.role, 'user');
      expect(copy.traceId, 10);
    });

    test('copyWith clearTraceId sets traceId to null', () {
      final msg = AiChatMessage(role: 'user', content: 'x', traceId: 42);
      final copy = msg.copyWith(clearTraceId: true);

      expect(copy.traceId, isNull);
    });

    test('copyWith clearUserRating sets userRating to null', () {
      final msg =
          AiChatMessage(role: 'user', content: 'x', userRating: 'like');
      final copy = msg.copyWith(clearUserRating: true);

      expect(copy.userRating, isNull);
    });

    test('copyWith clearConfidence sets confidence to null', () {
      final msg =
          AiChatMessage(role: 'assistant', content: 'x', confidence: 0.9);
      final copy = msg.copyWith(clearConfidence: true);

      expect(copy.confidence, isNull);
    });

    test('copyWith clearGroundingScore sets groundingScore to null', () {
      final msg =
          AiChatMessage(role: 'assistant', content: 'x', groundingScore: 0.7);
      final copy = msg.copyWith(clearGroundingScore: true);

      expect(copy.groundingScore, isNull);
    });

    test('copyWith with no args returns equivalent copy', () {
      final msg = AiChatMessage(
        role: 'error',
        content: 'Oops',
        errorType: 'network_error',
      );
      final copy = msg.copyWith();

      expect(copy.role, msg.role);
      expect(copy.content, msg.content);
      expect(copy.errorType, msg.errorType);
    });
  });

  group('AiConversationSummary.fromJson', () {
    test('parses fully-populated JSON correctly', () {
      final json = {
        'id': 'conv-abc-123',
        'title': 'Data analysis chat',
        'updated_at': '2025-06-15T10:00:00.000Z',
        'last_message_at': '2025-06-15T10:05:00.000Z',
      };

      final s = AiConversationSummary.fromJson(json);

      expect(s.id, 'conv-abc-123');
      expect(s.title, 'Data analysis chat');
      expect(s.updatedAt, DateTime.parse('2025-06-15T10:00:00.000Z'));
      expect(s.lastMessageAt, DateTime.parse('2025-06-15T10:05:00.000Z'));
    });

    test('handles missing optional fields', () {
      final s = AiConversationSummary.fromJson(<String, dynamic>{});

      expect(s.id, '');
      expect(s.title, isNull);
      expect(s.updatedAt, isNull);
      expect(s.lastMessageAt, isNull);
    });

    test('converts numeric id to string', () {
      final s = AiConversationSummary.fromJson({'id': 42});
      expect(s.id, '42');
    });

    test('handles malformed date strings gracefully', () {
      final s = AiConversationSummary.fromJson({
        'id': '1',
        'updated_at': 'not-a-date',
      });

      expect(s.updatedAt, isNull);
    });

    test('parses only updated_at when last_message_at is missing', () {
      final s = AiConversationSummary.fromJson({
        'id': '1',
        'updated_at': '2025-01-01T00:00:00.000Z',
      });

      expect(s.updatedAt, isNotNull);
      expect(s.lastMessageAt, isNull);
    });
  });
}
