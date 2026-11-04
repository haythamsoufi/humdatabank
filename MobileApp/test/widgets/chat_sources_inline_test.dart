import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/utils/ai_chat_message_html_split.dart';
import 'package:hum_databank_app/widgets/chat_response_sources_details_extension.dart';

const _backendHtml =
    '<p>Here is the trend.</p>\n<p>Caveat: text.</p>\n'
    '<p><strong><details class="chat-response-sources mt-2 border border-gray-200 rounded p-2 bg-gray-50">'
    '<summary class="cursor-pointer font-medium text-gray-700">Sources</summary>'
    '<div class="chat-response-sources-body mt-2 text-sm text-gray-600">- '
    '<a href="/api/ai/documents/12/download" class="text-blue-600">Syria UPR 2026 - page 14</a>: '
    '&#34;Volunteers reached 14,098.&#34;<br>- Databank: Number of people</div></details></strong></p>';

void main() {
  testWidgets('sources chip is not rendered inline after the split', (tester) async {
    final split = splitAssistantHtmlForVisualsAfterBody(_backendHtml);
    expect(split.trailingSourcesHtml, isNotNull);

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [AppLocalizations.delegate],
        supportedLocales: const [Locale('en')],
        home: Scaffold(
          body: Html(
            data: split.mainHtml,
            extensions: const [ChatResponseSourcesDetailsExtension()],
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('Sources'), findsNothing);
    expect(find.textContaining('Caveat'), findsOneWidget);
  });
}
