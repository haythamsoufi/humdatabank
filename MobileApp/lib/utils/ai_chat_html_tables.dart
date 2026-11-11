import 'package:html/dom.dart' as dom;
import 'package:html/parser.dart' as html_parser;

/// One cell from an assistant-message HTML `<table>`.
class AiChatHtmlTableCell {
  final String text;
  final String? href;

  const AiChatHtmlTableCell({
    required this.text,
    this.href,
  });
}

/// Parsed HTML table for native Flutter rendering (flutter_html 3.x does not
/// render `<table>` without a separate extension).
class AiChatHtmlTableData {
  final List<AiChatHtmlTableCell> headers;
  final List<List<AiChatHtmlTableCell>> rows;

  const AiChatHtmlTableData({
    required this.headers,
    required this.rows,
  });

  bool get isEmpty => headers.isEmpty && rows.isEmpty;
}

/// Narrative HTML or a lifted table, in document order.
sealed class AiChatHtmlSegment {
  const AiChatHtmlSegment();
}

class AiChatHtmlMarkupSegment extends AiChatHtmlSegment {
  final String html;

  const AiChatHtmlMarkupSegment(this.html);
}

class AiChatHtmlTableSegment extends AiChatHtmlSegment {
  final AiChatHtmlTableData table;

  const AiChatHtmlTableSegment(this.table);
}

String _cellPlain(dom.Element cell) {
  return cell.text.replaceAll(RegExp(r'\s+'), ' ').trim();
}

AiChatHtmlTableCell _parseCell(dom.Element cell) {
  final anchor = cell.querySelector('a[href]');
  if (anchor != null) {
    final href = (anchor.attributes['href'] ?? '').trim();
    final label = _cellPlain(anchor);
    final fallback = _cellPlain(cell);
    return AiChatHtmlTableCell(
      text: label.isNotEmpty ? label : fallback,
      href: href.isEmpty ? null : href,
    );
  }
  return AiChatHtmlTableCell(text: _cellPlain(cell));
}

List<AiChatHtmlTableCell> _cellsInRow(dom.Element row) {
  return row.children
      .where((c) => c.localName == 'th' || c.localName == 'td')
      .map(_parseCell)
      .toList();
}

AiChatHtmlTableData parseHtmlTableElement(dom.Element table) {
  final headerRows = <List<AiChatHtmlTableCell>>[];
  final bodyRows = <List<AiChatHtmlTableCell>>[];

  for (final child in table.children) {
    final tag = child.localName;
    if (tag == 'thead') {
      for (final tr in child.children.where((e) => e.localName == 'tr')) {
        final cells = _cellsInRow(tr);
        if (cells.isNotEmpty) headerRows.add(cells);
      }
    } else if (tag == 'tbody' || tag == 'tfoot') {
      for (final tr in child.children.where((e) => e.localName == 'tr')) {
        final cells = _cellsInRow(tr);
        if (cells.isNotEmpty) bodyRows.add(cells);
      }
    } else if (tag == 'tr') {
      final cells = _cellsInRow(child);
      if (cells.isEmpty) continue;
      final isHeader = child.children.any((c) => c.localName == 'th');
      if (isHeader && headerRows.isEmpty && bodyRows.isEmpty) {
        headerRows.add(cells);
      } else {
        bodyRows.add(cells);
      }
    }
  }

  // Fallback: some sanitizers flatten thead/tbody away but leave tr descendants.
  if (headerRows.isEmpty && bodyRows.isEmpty) {
    for (final tr in table.querySelectorAll('tr')) {
      final cells = _cellsInRow(tr);
      if (cells.isEmpty) continue;
      final isHeader = tr.children.any((c) => c.localName == 'th');
      if (isHeader && headerRows.isEmpty && bodyRows.isEmpty) {
        headerRows.add(cells);
      } else {
        bodyRows.add(cells);
      }
    }
  }

  List<AiChatHtmlTableCell> headers;
  List<List<AiChatHtmlTableCell>> rows;
  if (headerRows.isNotEmpty) {
    headers = headerRows.first;
    rows = [...headerRows.skip(1), ...bodyRows];
  } else if (bodyRows.isNotEmpty) {
    headers = bodyRows.first;
    rows = bodyRows.skip(1).toList();
  } else {
    headers = const [];
    rows = const [];
  }

  final colCount = headers.length;
  if (colCount > 0) {
    rows = rows.map((r) {
      if (r.length == colCount) return r;
      if (r.length > colCount) return r.sublist(0, colCount);
      return [...r, ...List.filled(colCount - r.length, const AiChatHtmlTableCell(text: ''))];
    }).toList();
  }

  return AiChatHtmlTableData(headers: headers, rows: rows);
}

void _appendNodeHtml(StringBuffer buf, dom.Node node) {
  if (node is dom.Text) {
    buf.write(node.text);
    return;
  }
  if (node is dom.Element) {
    buf.write(node.outerHtml);
  }
}

/// Splits assistant HTML so `<table>` blocks can be rendered natively.
///
/// Nested tables inside a wrapper (e.g. `<div><table>…</table></div>`) are
/// lifted in document order; non-table siblings stay as HTML markup segments.
List<AiChatHtmlSegment> splitAssistantHtmlTables(String? raw) {
  final source = raw ?? '';
  if (source.trim().isEmpty) {
    return const [];
  }
  if (!source.toLowerCase().contains('<table')) {
    return [AiChatHtmlMarkupSegment(source)];
  }

  final fragment = html_parser.parseFragment(source);
  final segments = <AiChatHtmlSegment>[];
  final htmlBuf = StringBuffer();

  void flushHtml() {
    final chunk = htmlBuf.toString();
    htmlBuf.clear();
    if (chunk.trim().isEmpty) return;
    segments.add(AiChatHtmlMarkupSegment(chunk));
  }

  void walk(List<dom.Node> nodes) {
    for (final node in nodes) {
      if (node is dom.Element && node.localName == 'table') {
        flushHtml();
        final table = parseHtmlTableElement(node);
        if (!table.isEmpty) {
          segments.add(AiChatHtmlTableSegment(table));
        }
        continue;
      }
      if (node is dom.Element && node.querySelector('table') != null) {
        // Preserve order: emit preceding non-table siblings as HTML, lift tables.
        for (final child in node.nodes) {
          if (child is dom.Element && child.localName == 'table') {
            flushHtml();
            final table = parseHtmlTableElement(child);
            if (!table.isEmpty) {
              segments.add(AiChatHtmlTableSegment(table));
            }
          } else if (child is dom.Element && child.querySelector('table') != null) {
            walk([child]);
          } else {
            _appendNodeHtml(htmlBuf, child);
          }
        }
        continue;
      }
      _appendNodeHtml(htmlBuf, node);
    }
  }

  walk(fragment.nodes);
  flushHtml();
  if (segments.isEmpty) {
    return [AiChatHtmlMarkupSegment(source)];
  }
  return segments;
}
