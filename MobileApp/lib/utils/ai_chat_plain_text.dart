import 'package:html/dom.dart' as dom;
import 'package:html/parser.dart' as html_parser;

const Set<String> _blockTags = {
  'p',
  'div',
  'section',
  'article',
  'header',
  'footer',
  'blockquote',
  'pre',
  'ul',
  'ol',
  'details',
  'summary',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'table',
  'hr',
};

const Set<String> _skippedTags = {'script', 'style', 'head', 'template'};

/// Converts an assistant chat message (HTML fragment from the Backoffice) into
/// clean plain text suitable for the clipboard: no tags, entities decoded,
/// list items prefixed with "- " / "N. ", table rows as tab-separated lines.
String aiChatHtmlToPlainText(String? raw) {
  final source = raw ?? '';
  if (source.trim().isEmpty) return '';
  if (!source.contains('<') && !source.contains('&')) {
    return source.trim();
  }

  final out = StringBuffer();
  final fragment = html_parser.parseFragment(source);
  _walk(fragment.nodes, out);

  return out
      .toString()
      .replaceAll('\u00A0', ' ')
      .split('\n')
      .map((line) => line.replaceAll(RegExp(r'^ +| +$'), ''))
      .join('\n')
      .replaceAll(RegExp(r'\n{3,}'), '\n\n')
      .trim();
}

void _ensureNewline(StringBuffer out) {
  final s = out.toString();
  if (s.isNotEmpty && !s.endsWith('\n')) out.write('\n');
}

void _ensureBlankLine(StringBuffer out) {
  final s = out.toString();
  if (s.isEmpty) return;
  if (s.endsWith('\n\n')) return;
  out.write(s.endsWith('\n') ? '\n' : '\n\n');
}

void _walk(List<dom.Node> nodes, StringBuffer out) {
  for (final node in nodes) {
    if (node is dom.Text) {
      out.write(node.text.replaceAll(RegExp(r'\s+'), ' '));
      continue;
    }
    if (node is! dom.Element) continue;

    final tag = node.localName ?? '';
    if (_skippedTags.contains(tag)) continue;

    switch (tag) {
      case 'br':
        out.write('\n');
        break;
      case 'ul':
        _ensureNewline(out);
        _walkList(node, out, ordered: false);
        _ensureNewline(out);
        break;
      case 'ol':
        _ensureNewline(out);
        _walkList(node, out, ordered: true);
        _ensureNewline(out);
        break;
      case 'table':
        _ensureBlankLine(out);
        _walkTable(node, out);
        _ensureBlankLine(out);
        break;
      default:
        final isBlock = _blockTags.contains(tag);
        if (isBlock) _ensureBlankLine(out);
        _walk(node.nodes, out);
        if (isBlock) _ensureBlankLine(out);
    }
  }
}

void _walkList(dom.Element list, StringBuffer out, {required bool ordered}) {
  var index = 1;
  for (final child in list.children) {
    if (child.localName != 'li') continue;
    _ensureNewline(out);
    out.write(ordered ? '${index++}. ' : '- ');
    _walk(child.nodes, out);
  }
}

void _walkTable(dom.Element table, StringBuffer out) {
  for (final row in table.querySelectorAll('tr')) {
    final cells = row.children
        .where((c) => c.localName == 'td' || c.localName == 'th')
        .map((c) => c.text.replaceAll(RegExp(r'\s+'), ' ').trim())
        .toList();
    if (cells.isEmpty) continue;
    out.writeln(cells.join('\t'));
  }
}
