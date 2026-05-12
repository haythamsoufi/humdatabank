import 'package:html/dom.dart' as dom;
import 'package:html/parser.dart' as html_parser;

/// Result of [splitAssistantHtmlForVisualsAfterBody].
class AiChatAssistantDisplayHtmlSplit {
  final String mainHtml;
  final String? trailingSourcesHtml;

  const AiChatAssistantDisplayHtmlSplit({
    required this.mainHtml,
    this.trailingSourcesHtml,
  });
}

/// Removes `.chat-response-sources` blocks (details or div) from the narrative HTML
/// so they can be rendered **after** charts/maps/tables. Matches Backoffice: Sources
/// should sit at the bottom of the response when structured visuals are present.
AiChatAssistantDisplayHtmlSplit splitAssistantHtmlForVisualsAfterBody(String? raw) {
  final s = raw ?? '';
  if (s.trim().isEmpty) {
    return const AiChatAssistantDisplayHtmlSplit(mainHtml: '');
  }
  final fragment = html_parser.parseFragment(s);
  final found = List<dom.Element>.from(
    fragment.querySelectorAll('details.chat-response-sources, div.chat-response-sources'),
  );
  if (found.isEmpty) {
    return AiChatAssistantDisplayHtmlSplit(mainHtml: s, trailingSourcesHtml: null);
  }
  final trailing = StringBuffer();
  for (final el in found) {
    trailing.write(el.outerHtml);
  }
  for (final el in found) {
    el.remove();
  }
  return AiChatAssistantDisplayHtmlSplit(
    mainHtml: fragment.outerHtml,
    trailingSourcesHtml: trailing.isEmpty ? null : trailing.toString(),
  );
}
