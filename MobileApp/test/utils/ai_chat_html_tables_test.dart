import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/utils/ai_chat_html_tables.dart';

void main() {
  test('leaves table-free HTML as a single markup segment', () {
    const raw = '<p>Hello Syria.</p>';
    final segments = splitAssistantHtmlTables(raw);
    expect(segments, hasLength(1));
    expect(segments.single, isA<AiChatHtmlMarkupSegment>());
    expect((segments.single as AiChatHtmlMarkupSegment).html, raw);
  });

  test('lifts a markdown-converted emergency documents table', () {
    const raw = '''
<p>Here are the emergency operation documents the public catalog has for Syria (showing every returned row; total results = 23).</p>
<table>
<thead>
<tr><th>Title</th><th>Category</th><th>Date</th><th>Link</th></tr>
</thead>
<tbody>
<tr>
  <td>Syria - Fire (MDRSY013)</td>
  <td>emergency_operation</td>
  <td>2024-01-01</td>
  <td><a href="https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr">Download</a></td>
</tr>
<tr>
  <td>Syria - Wildfires (MDRSY015)</td>
  <td>emergency_operation</td>
  <td>2025-01-01</td>
  <td><a href="https://go-api.ifrc.org/api/DownloadFile/92291/MDRSY015FR">Download</a></td>
</tr>
</tbody>
</table>
''';
    final segments = splitAssistantHtmlTables(raw);
    expect(segments, hasLength(2));
    expect(segments[0], isA<AiChatHtmlMarkupSegment>());
    expect(
      (segments[0] as AiChatHtmlMarkupSegment).html,
      contains('emergency operation documents'),
    );
    expect(segments[1], isA<AiChatHtmlTableSegment>());
    final table = (segments[1] as AiChatHtmlTableSegment).table;
    expect(table.headers.map((c) => c.text).toList(), [
      'Title',
      'Category',
      'Date',
      'Link',
    ]);
    expect(table.rows, hasLength(2));
    expect(table.rows[0][0].text, 'Syria - Fire (MDRSY013)');
    expect(table.rows[0][3].text, 'Download');
    expect(
      table.rows[0][3].href,
      'https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr',
    );
    expect(table.rows[1][0].text, 'Syria - Wildfires (MDRSY015)');
  });

  test('preserves prose after a lifted table', () {
    const raw = '<p>Intro</p><table><tr><th>A</th></tr><tr><td>1</td></tr></table><p>Outro</p>';
    final segments = splitAssistantHtmlTables(raw);
    expect(segments, hasLength(3));
    expect((segments[0] as AiChatHtmlMarkupSegment).html, contains('Intro'));
    expect(segments[1], isA<AiChatHtmlTableSegment>());
    expect((segments[2] as AiChatHtmlMarkupSegment).html, contains('Outro'));
  });

  test('parses flat tr rows when thead/tbody are absent', () {
    const raw =
        '<table><tr><th>Year</th><th>Value</th></tr><tr><td>2024</td><td>47</td></tr></table>';
    final segments = splitAssistantHtmlTables(raw);
    expect(segments, hasLength(1));
    final table = (segments.single as AiChatHtmlTableSegment).table;
    expect(table.headers.map((c) => c.text).toList(), ['Year', 'Value']);
    expect(table.rows.single.map((c) => c.text).toList(), ['2024', '47']);
  });
}
