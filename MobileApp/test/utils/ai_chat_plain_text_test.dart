import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/utils/ai_chat_plain_text.dart';

void main() {
  group('aiChatHtmlToPlainText', () {
    test('strips tags and decodes entities from a typical assistant reply', () {
      const html = '<p>Kenya — Number of branches: 47. [Plan, p.1]</p>\n'
          '<p>Note: the lookup returned an error.</p>\n'
          '<p><strong><details class="chat-response-sources mt-2">'
          '<summary class="cursor-pointer">Sources</summary>'
          '<div class="chat-response-sources-body mt-2">- '
          '<a href="/api/ai/documents/1156/download" target="_blank">Kenya 2024 Unified Plan - page 1</a>'
          ': extracted UPR KPI &#39;branches&#39; = 47 (confidence 0.93).</div>'
          '</details></strong></p>';

      final text = aiChatHtmlToPlainText(html);

      expect(text, isNot(contains('<')));
      expect(text, isNot(contains('&#39;')));
      expect(text, contains('Kenya — Number of branches: 47. [Plan, p.1]'));
      expect(text, contains('Note: the lookup returned an error.'));
      expect(text, contains("extracted UPR KPI 'branches' = 47"));
      expect(
        text.split('\n').first,
        'Kenya — Number of branches: 47. [Plan, p.1]',
      );
    });

    test('formats lists and line breaks', () {
      final text = aiChatHtmlToPlainText(
        '<p>Intro</p><ul><li>One</li><li>Two</li></ul>'
        '<ol><li>First</li><li>Second</li></ol>a<br>b',
      );

      expect(text, contains('- One\n- Two'));
      expect(text, contains('1. First\n2. Second'));
      expect(text, endsWith('a\nb'));
    });

    test('formats tables as tab-separated rows', () {
      final text = aiChatHtmlToPlainText(
        '<table><tr><th>Year</th><th>Value</th></tr>'
        '<tr><td>2024</td><td>47</td></tr></table>',
      );

      expect(text, 'Year\tValue\n2024\t47');
    });

    test('returns plain text unchanged and handles empty input', () {
      expect(aiChatHtmlToPlainText('Just text'), 'Just text');
      expect(aiChatHtmlToPlainText(null), '');
      expect(aiChatHtmlToPlainText('   '), '');
    });
  });
}
