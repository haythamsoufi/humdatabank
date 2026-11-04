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

/// Drops trailing `<br>`, empty paragraphs/divs and `&nbsp;` so no blank space is left
/// below the last line of narrative text.
String trimTrailingEmptyHtml(String html) {
  return html.replaceFirst(
    RegExp(
      r'(?:\s|&nbsp;|<br\s*/?>|<(p|div)[^>]*>(?:\s|&nbsp;|<br\s*/?>|<(strong|b|em|i|span)[^>]*>\s*</\2>)*</\1>)+$',
      caseSensitive: false,
    ),
    '',
  );
}

/// Removes empty `<p>`/`<strong>`/... left behind when a block is lifted out; an empty
/// paragraph still renders a blank line plus margins.
void _pruneEmptyWrappers(dom.Node root) {
  const tags = {'p', 'div', 'strong', 'b', 'em', 'i', 'span'};
  var removed = true;
  while (removed) {
    removed = false;
    final empties = root
        .nodes
        .expand<dom.Element>(_descendantElements)
        .where((e) => tags.contains(e.localName) && e.children.isEmpty && e.text.trim().isEmpty)
        .toList();
    for (final e in empties) {
      e.remove();
      removed = true;
    }
  }
}

Iterable<dom.Element> _descendantElements(dom.Node n) sync* {
  if (n is dom.Element) {
    yield n;
    for (final c in n.nodes) {
      yield* _descendantElements(c);
    }
  }
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
  _pruneEmptyWrappers(fragment);
  return AiChatAssistantDisplayHtmlSplit(
    mainHtml: fragment.outerHtml,
    trailingSourcesHtml: trailing.isEmpty ? null : trailing.toString(),
  );
}
