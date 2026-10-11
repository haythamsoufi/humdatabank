import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/utils/sse_event_parser.dart';

List<Map<String, dynamic>> _feed(SseEventParser parser, List<String> lines) {
  final events = <Map<String, dynamic>>[];
  for (final line in lines) {
    final event = parser.addLine(line);
    if (event != null) events.add(event);
  }
  final tail = parser.flush();
  if (tail != null) events.add(tail);
  return events;
}

void main() {
  group('SseEventParser', () {
    test('emits one event per blank-line-terminated data block', () {
      final events = _feed(SseEventParser(), [
        'data: {"type":"meta","request_id":"r1"}',
        '',
        'data: {"type":"step","message":"Searching"}',
        '',
      ]);

      expect(events, [
        {'type': 'meta', 'request_id': 'r1'},
        {'type': 'step', 'message': 'Searching'},
      ]);
    });

    test('accepts data without a space after the colon', () {
      final events = _feed(SseEventParser(), ['data:{"type":"delta","text":"hi"}', '']);

      expect(events, [
        {'type': 'delta', 'text': 'hi'},
      ]);
    });

    test('joins multi-line data fields with a newline', () {
      final events = _feed(SseEventParser(), [
        'data: {"type":"delta",',
        'data: "text":"a"}',
        '',
      ]);

      expect(events, [
        {'type': 'delta', 'text': 'a'},
      ]);
    });

    test('ignores comments, other fields and blank keep-alives', () {
      final events = _feed(SseEventParser(), [
        ': keep-alive',
        'event: message',
        'id: 7',
        '',
        '',
        'data: {"type":"heartbeat"}',
        '',
      ]);

      expect(events, [
        {'type': 'heartbeat'},
      ]);
    });

    test('flushes a final event that has no trailing blank line', () {
      final events = _feed(SseEventParser(), ['data: {"type":"done","response":"ok"}']);

      expect(events, [
        {'type': 'done', 'response': 'ok'},
      ]);
    });

    test('skips malformed and non-object payloads and keeps parsing', () {
      final events = _feed(SseEventParser(), [
        'data: {not json',
        '',
        'data: [1,2]',
        '',
        'data: {"type":"done"}',
        '',
      ]);

      expect(events, [
        {'type': 'done'},
      ]);
    });
  });
}
