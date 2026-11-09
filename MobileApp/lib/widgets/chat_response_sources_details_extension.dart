import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:html/dom.dart' as html;
import 'package:html/parser.dart' as html_parser;

import '../l10n/app_localizations.dart';
import '../theme/chat_immersive_palette.dart';
import 'sheets/native_modal_sheet.dart';

/// One parsed entry from a `<details class="chat-response-sources">` block.
class ChatResponseSourceItem {
  const ChatResponseSourceItem({
    required this.title,
    this.page,
    this.url,
    this.excerpt,
  });

  final String title;
  final String? page;
  final String? url;
  final String? excerpt;

  ChatResponseSourceItem withExcerpt(String more) => ChatResponseSourceItem(
        title: title,
        page: page,
        url: url,
        excerpt: (excerpt == null || excerpt!.isEmpty) ? more : '$excerpt $more',
      );
}

class ChatResponseSourcesParsed {
  const ChatResponseSourcesParsed(this.items, this.notes);

  final List<ChatResponseSourceItem> items;

  /// Answer-verification caveats; shown under the list, not counted as sources.
  final List<String> notes;
}

String _squash(String s) => s.replaceAll(RegExp(r'\s+'), ' ').trim();

/// [Backoffice] `ai_answer_verifier.py` appends a caveat that may sit in the sources list.
bool _isAnswerVerificationCaveat(String plain) {
  final t = _squash(plain).toLowerCase();
  if (t.isEmpty) return false;
  return t.contains('could not be verified against the available sources') ||
      ((t.startsWith('note:') || t.startsWith('> note:')) &&
          t.contains('could not be verified'));
}

ChatResponseSourceItem? _itemFromDataAttrs(html.Element el) {
  final title = _squash(el.attributes['data-source-title'] ?? '');
  if (title.isEmpty) return null;
  final detail = _squash(el.attributes['data-source-detail'] ?? '');
  final urlRaw = (el.attributes['data-source-url'] ?? '').trim();
  final pageRaw = (el.attributes['data-source-page'] ?? '').trim();
  return ChatResponseSourceItem(
    title: title,
    page: pageRaw.isEmpty ? null : pageRaw,
    url: urlRaw.isEmpty ? null : urlRaw,
    excerpt: detail.isEmpty ? null : detail,
  );
}

List<ChatResponseSourceItem> _parseStructuredSourceRows(html.Element body) {
  final items = <ChatResponseSourceItem>[];
  for (final el in body.querySelectorAll('[data-source-title]')) {
    final item = _itemFromDataAttrs(el);
    if (item != null) items.add(item);
  }
  return items;
}

/// Parses `.chat-response-sources-body` from structured `data-source-*` rows only.
ChatResponseSourcesParsed parseChatResponseSources(html.Element? details) {
  final items = <ChatResponseSourceItem>[];
  final notes = <String>[];
  if (details == null) return ChatResponseSourcesParsed(items, notes);
  final bodies = details.getElementsByClassName('chat-response-sources-body');
  if (bodies.isEmpty) return ChatResponseSourcesParsed(items, notes);
  final body = bodies.first;

  final structured = _parseStructuredSourceRows(body);
  if (structured.isEmpty) {
    return ChatResponseSourcesParsed(items, notes);
  }

  for (final el in body.querySelectorAll('li, p')) {
    if (el.attributes.containsKey('data-source-title')) continue;
    final plain = _squash(el.text);
    if (_isAnswerVerificationCaveat(plain)) {
      notes.add(plain.replaceFirst(RegExp(r'^>?\s*'), ''));
    }
  }
  return ChatResponseSourcesParsed(structured, notes);
}

bool _isEnglishSourcesSummary(String plain) {
  return RegExp(r'^Sources(\s*\(\d+\))?\s*$', caseSensitive: false)
      .hasMatch(plain.trim());
}

String _summaryPlainText(html.Element? details) {
  if (details == null) return 'Sources';
  final summaries = details.getElementsByTagName('summary');
  if (summaries.isEmpty) return 'Sources';
  final t = summaries.first.text.trim();
  return t.isEmpty ? 'Sources' : t;
}

/// Renders `<details class="chat-response-sources">` as a "Sources N" chip that opens a bottom sheet.
class ChatResponseSourcesDetailsExtension extends HtmlExtension {
  const ChatResponseSourcesDetailsExtension({this.onOpenLink});

  /// Called with a source URL (internal path or http link) when the user taps a source.
  final void Function(String url)? onOpenLink;

  @override
  Set<String> get supportedTags => {'details'};

  @override
  bool matches(ExtensionContext context) {
    return context.elementName == 'details' &&
        context.classes.contains('chat-response-sources');
  }

  @override
  StyledElement prepare(
    ExtensionContext context,
    List<StyledElement> children,
  ) {
    return StyledElement(
      name: context.elementName,
      children: children,
      style: Style(),
      node: context.node,
    );
  }

  @override
  InlineSpan build(ExtensionContext context) {
    final details = context.element;
    return WidgetSpan(
      alignment: PlaceholderAlignment.top,
      child: _SourcesChip(
        parsed: parseChatResponseSources(details),
        summaryPlain: _summaryPlainText(details),
        onOpenLink: onOpenLink,
      ),
    );
  }
}

/// Standalone "Sources N" button for a message's sources block (e.g. in the action row).
class ChatResponseSourcesButton extends StatelessWidget {
  const ChatResponseSourcesButton({
    super.key,
    required this.sourcesHtml,
    this.onOpenLink,
  });

  final String sourcesHtml;
  final void Function(String url)? onOpenLink;

  @override
  Widget build(BuildContext context) {
    final details = html_parser
        .parseFragment(sourcesHtml)
        .querySelector('details.chat-response-sources, div.chat-response-sources');
    return _SourcesChip(
      parsed: parseChatResponseSources(details),
      summaryPlain: _summaryPlainText(details),
      onOpenLink: onOpenLink,
      compact: true,
    );
  }
}

class _SourcesChip extends StatelessWidget {
  const _SourcesChip({
    required this.parsed,
    required this.summaryPlain,
    required this.onOpenLink,
    this.compact = false,
  });

  final ChatResponseSourcesParsed parsed;
  final String summaryPlain;
  final void Function(String url)? onOpenLink;
  final bool compact;

  void _openSheet(BuildContext context) {
    final theme = Theme.of(context);
    final loc = AppLocalizations.of(context)!;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) => NativeModalSheetScaffold(
        theme: theme,
        title: _label(loc),
        closeTooltip: loc.close,
        bodyExpands: false,
        onClose: () => Navigator.pop(sheetContext),
        child: _SourcesList(
          parsed: parsed,
          onOpen: (url) {
            Navigator.pop(sheetContext);
            onOpenLink?.call(url);
          },
        ),
      ),
    );
  }

  String _label(AppLocalizations loc) => _isEnglishSourcesSummary(summaryPlain)
      ? loc.aiResponseSources
      : summaryPlain.replaceAll(RegExp(r'\s*[(（]\d+[)）]\s*$'), '');

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final dark = theme.brightness == Brightness.dark;
    final muted =
        dark ? ChatImmersivePalette.darkMuted : cs.onSurfaceVariant;
    final body = dark ? ChatImmersivePalette.darkText : cs.onSurface;
    final fill = dark ? ChatImmersivePalette.darkRaised : cs.surfaceContainerHigh;
    final outline = dark ? ChatImmersivePalette.darkBorder : cs.outline;
    final count = parsed.items.length;

    return Padding(
      padding: compact ? EdgeInsets.zero : const EdgeInsets.only(top: 4, bottom: 2),
      child: Material(
        color: compact ? Colors.transparent : fill,
        shape: StadiumBorder(
          side: compact
              ? BorderSide.none
              : BorderSide(color: outline.withValues(alpha: 0.5), width: 0.8),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => _openSheet(context),
          child: Padding(
            padding: compact
                ? const EdgeInsets.fromLTRB(6, 6, 4, 6)
                : const EdgeInsets.fromLTRB(12, 7, 8, 7),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!compact) ...[
                  Icon(Icons.menu_book_outlined, size: 16, color: muted),
                  const SizedBox(width: 8),
                ],
                Text(
                  _label(loc),
                  style: TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.1,
                    height: 1.2,
                    color: body,
                  ),
                ),
                if (count > 0) ...[
                  const SizedBox(width: 8),
                  Container(
                    constraints:
                        const BoxConstraints(minWidth: 20, minHeight: 20),
                    padding: const EdgeInsets.symmetric(horizontal: 6),
                    decoration: BoxDecoration(
                      color: cs.primary.withValues(alpha: dark ? 0.28 : 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    alignment: Alignment.center,
                    child: Text(
                      '$count',
                      style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.w700,
                        height: 1.1,
                        color: dark ? body : cs.primary,
                      ),
                    ),
                  ),
                ],
                const SizedBox(width: 2),
                Icon(Icons.chevron_right, size: 18, color: muted),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SourcesList extends StatelessWidget {
  const _SourcesList({required this.parsed, required this.onOpen});

  final ChatResponseSourcesParsed parsed;
  final void Function(String url) onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final muted = cs.onSurfaceVariant;

    return ListView(
      shrinkWrap: true,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      children: [
        for (var i = 0; i < parsed.items.length; i++)
          _SourceTile(
            index: i + 1,
            item: parsed.items[i],
            onOpen: onOpen,
          ),
        for (final note in parsed.notes)
          Padding(
            padding: const EdgeInsets.fromLTRB(4, 12, 4, 0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.info_outline, size: 16, color: muted),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    note,
                    style: TextStyle(fontSize: 12.5, height: 1.4, color: muted),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _SourceTile extends StatelessWidget {
  const _SourceTile({
    required this.index,
    required this.item,
    required this.onOpen,
  });

  final int index;
  final ChatResponseSourceItem item;
  final void Function(String url) onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final url = item.url;

    return InkWell(
      onTap: url == null ? null : () => onOpen(url),
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 24,
              height: 24,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: cs.primary.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Text(
                '$index',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: cs.primary,
                ),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    item.title,
                    style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w600,
                      height: 1.3,
                      color: cs.onSurface,
                    ),
                  ),
                  if (item.page != null) ...[
                    const SizedBox(height: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 2,
                      ),
                      decoration: BoxDecoration(
                        color: cs.onSurface.withValues(alpha: 0.07),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'p. ${item.page}',
                        style: TextStyle(
                          fontSize: 11.5,
                          fontWeight: FontWeight.w600,
                          color: cs.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ],
                  if (item.excerpt != null) ...[
                    const SizedBox(height: 6),
                    Text(
                      item.excerpt!,
                      maxLines: 6,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 13,
                        height: 1.4,
                        color: cs.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (url != null)
              Padding(
                padding: const EdgeInsets.only(left: 8, top: 2),
                child: Icon(
                  Icons.open_in_new_rounded,
                  size: 18,
                  color: cs.primary,
                ),
              ),
          ],
        ),
      ),
    );
  }
}
