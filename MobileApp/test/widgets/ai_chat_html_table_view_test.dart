import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/utils/ai_chat_html_tables.dart';
import 'package:hum_databank_app/widgets/ai_chat_html_table_view.dart';

void main() {
  testWidgets('renders table headers, rows, and tappable download links', (tester) async {
    String? tappedUrl;
    String? tappedLabel;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AiChatHtmlTableView(
            table: const AiChatHtmlTableData(
              headers: [
                AiChatHtmlTableCell(text: 'Title'),
                AiChatHtmlTableCell(text: 'Link'),
              ],
              rows: [
                [
                  AiChatHtmlTableCell(text: 'Syria - Fire (MDRSY013)'),
                  AiChatHtmlTableCell(
                    text: 'Download',
                    href: 'https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr',
                  ),
                ],
              ],
            ),
            onLinkTap: (url, {linkText}) {
              tappedUrl = url;
              tappedLabel = linkText;
            },
          ),
        ),
      ),
    );

    expect(find.text('Title'), findsOneWidget);
    expect(find.text('Syria - Fire (MDRSY013)'), findsOneWidget);
    expect(find.text('Download'), findsOneWidget);
    expect(find.byType(InkWell), findsOneWidget);

    // Table + horizontal scroll can miss hit tests in widget tests; invoke onTap directly.
    final inkWell = tester.widget<InkWell>(find.byType(InkWell));
    inkWell.onTap!();
    await tester.pump();
    expect(
      tappedUrl,
      'https://go-api.ifrc.org/api/DownloadFile/89684/MDRSY013fr',
    );
    expect(tappedLabel, 'Download');
  });
}
