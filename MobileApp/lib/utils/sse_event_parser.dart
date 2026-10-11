import 'dart:convert';

/// Incremental parser for Server-Sent Events whose `data:` payload is a JSON object
/// (the Backoffice AI stream emits `data: {json}` blocks separated by blank lines).
///
/// Feed it one decoded line at a time with [addLine]; it returns a decoded event when a blank
/// line completes one. Comment lines (`:`), other SSE fields and malformed JSON are ignored.
class SseEventParser {
  final StringBuffer _data = StringBuffer();

  Map<String, dynamic>? addLine(String line) {
    if (line.isEmpty) return flush();
    if (line.startsWith('data:')) {
      var value = line.substring(5);
      if (value.startsWith(' ')) value = value.substring(1);
      if (_data.isNotEmpty) _data.write('\n');
      _data.write(value);
    }
    return null;
  }

  /// Emits any buffered event (call when the stream ends without a trailing blank line).
  Map<String, dynamic>? flush() {
    if (_data.isEmpty) return null;
    final raw = _data.toString();
    _data.clear();
    try {
      final decoded = jsonDecode(raw);
      if (decoded is Map) return Map<String, dynamic>.from(decoded);
    } catch (_) {
      // Ignore malformed events rather than aborting the whole stream.
    }
    return null;
  }
}
