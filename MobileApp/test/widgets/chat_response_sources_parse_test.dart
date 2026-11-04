import 'package:flutter_test/flutter_test.dart';
import 'package:html/parser.dart' as html_parser;
import 'package:hum_databank_app/widgets/chat_response_sources_details_extension.dart';

ChatResponseSourcesParsed _parse(String body) {
  final doc = html_parser.parseFragment(
    '<details class="chat-response-sources"><summary>Sources</summary>'
    '<div class="chat-response-sources-body">$body</div></details>',
  );
  return parseChatResponseSources(doc.querySelector('details'));
}

void main() {
  test('parses linked document sources with page and excerpt', () {
    final r = _parse(
      '- <a href="/api/ai/documents/12/download">Syria UPR 2026 - page 14</a>: '
      '"Volunteers reached 14,098."<br>'
      '- Databank: Number of people volunteering in Syria (2016-2026)',
    );
    expect(r.items.length, 2);
    expect(r.items[0].title, 'Syria UPR 2026');
    expect(r.items[0].page, '14');
    expect(r.items[0].url, '/api/ai/documents/12/download');
    expect(r.items[0].excerpt, 'Volunteers reached 14,098.');
    expect(r.items[1].title, startsWith('Databank'));
    expect(r.items[1].url, isNull);
  });

  test('moves the verification caveat out of the source count', () {
    final r = _parse(
      '<ul><li>Doc A</li><li>Note: part of this answer could not be verified '
      'against the available sources.</li></ul>',
    );
    expect(r.items.length, 1);
    expect(r.notes.length, 1);
  });

  test('unbulleted lines continue the previous entry', () {
    final r = _parse(
      '- <a href="/api/ai/documents/1/download">Doc, page 3</a><br>'
      'second line of excerpt<br>'
      '- Other source',
    );
    expect(r.items.length, 2);
    expect(r.items[0].page, '3');
    expect(r.items[0].excerpt, 'second line of excerpt');
  });
}
