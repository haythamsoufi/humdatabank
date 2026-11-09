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
  test('parses structured data-source rows', () {
    final r = _parse(
      '<ul class="chat-response-sources-list">'
      '<li data-source-title="Syria UPR 2026" data-source-page="14" '
      'data-source-url="/api/ai/documents/12/download" '
      'data-source-detail="Volunteers reached 14,098." data-source-kind="document">'
      'ignored'
      '</li>'
      '<li data-source-title="IFRC Network Databank (indicator: &quot;Volunteers&quot;)" '
      'data-source-detail="years 2016–2024" data-source-kind="databank">'
      'ignored'
      '</li></ul>',
    );
    expect(r.items.length, 2);
    expect(r.items[0].title, 'Syria UPR 2026');
    expect(r.items[0].page, '14');
    expect(r.items[0].url, '/api/ai/documents/12/download');
    expect(r.items[0].excerpt, 'Volunteers reached 14,098.');
    expect(r.items[1].title, contains('Volunteers'));
    expect(r.items[1].excerpt, 'years 2016–2024');
  });

  test('ignores unstructured prose sources', () {
    final r = _parse(
      '- <a href="/api/ai/documents/12/download">Syria UPR 2026 - page 14</a>: '
      '"Volunteers reached 14,098."',
    );
    expect(r.items, isEmpty);
  });

  test('keeps verification caveat notes alongside structured rows', () {
    final r = _parse(
      '<ul class="chat-response-sources-list">'
      '<li data-source-title="Doc A" data-source-kind="document">Doc A</li>'
      '</ul>'
      '<p>Note: part of this answer could not be verified '
      'against the available sources.</p>',
    );
    expect(r.items.length, 1);
    expect(r.notes.length, 1);
  });
}
