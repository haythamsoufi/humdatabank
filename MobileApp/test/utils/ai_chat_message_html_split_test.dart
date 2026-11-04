import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/utils/ai_chat_message_html_split.dart';

void main() {
  test('removing the sources block leaves no empty paragraph behind', () {
    const raw = '<p>Intro.</p>\n<p>Caveat text.</p>\n'
        '<p><strong><details class="chat-response-sources">'
        '<summary>Sources</summary>'
        '<div class="chat-response-sources-body">- Doc A<br>- Doc B</div>'
        '</details></strong></p>';
    final split = splitAssistantHtmlForVisualsAfterBody(raw);
    expect(split.trailingSourcesHtml, contains('chat-response-sources'));
    expect(split.mainHtml, isNot(contains('<strong>')));
    expect(RegExp(r'<p>\s*</p>').hasMatch(split.mainHtml), isFalse);
    expect(split.mainHtml, contains('Caveat text.'));
  });

  test('trimTrailingEmptyHtml strips empty wrappers with inline tags', () {
    expect(
      trimTrailingEmptyHtml('<p>Hi</p><p><strong></strong></p><br>'),
      '<p>Hi</p>',
    );
  });
}
