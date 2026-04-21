import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:html/dom.dart' as html;

import '../theme/chat_immersive_palette.dart';

/// Custom collapsible for `<details class="chat-response-sources">`.
///
/// Avoids [ExpansionTile]/[ListTile], which enforce large minimum heights and
/// theme backgrounds that looked like oversized padded bars in chat HTML.
///
/// Collapsed label: `Sources (N)`; expanded: `Sources` (count hidden while open).
class ChatResponseSourcesDetailsExtension extends HtmlExtension {
  const ChatResponseSourcesDetailsExtension();

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
    return WidgetSpan(
      alignment: PlaceholderAlignment.top,
      child: _ChatResponseSourcesDetailsTile(
        extensionContext: context,
      ),
    );
  }
}

String _summaryPlainText(html.Element? details) {
  if (details == null) return 'Sources';
  final summaries = details.getElementsByTagName('summary');
  if (summaries.isEmpty) return 'Sources';
  final t = summaries.first.text.trim();
  return t.isEmpty ? 'Sources' : t;
}

/// Counts items inside `.chat-response-sources-body`: prefers `<li>`; otherwise
/// non-empty segments split on `<br>`.
int _countSourcesInBody(html.Element? details) {
  if (details == null) return 0;
  final bodies = details.getElementsByClassName('chat-response-sources-body');
  if (bodies.isEmpty) return 0;
  final body = bodies.first;
  final lis = body.getElementsByTagName('li');
  if (lis.isNotEmpty) return lis.length;
  final raw = body.innerHtml;
  if (raw.trim().isEmpty) return 0;
  final segments = raw.split(RegExp(r'<br\s*/?>', caseSensitive: false));
  var count = 0;
  for (final seg in segments) {
    final plain = seg.replaceAll(RegExp(r'<[^>]+>'), '').trim();
    if (plain.isNotEmpty) count++;
  }
  return count > 0 ? count : 1;
}

bool _detailsInitiallyOpen(html.Element? details) {
  if (details == null) return false;
  return details.attributes.containsKey('open');
}

class _ChatResponseSourcesDetailsTile extends StatefulWidget {
  const _ChatResponseSourcesDetailsTile({
    required this.extensionContext,
  });

  final ExtensionContext extensionContext;

  @override
  State<_ChatResponseSourcesDetailsTile> createState() =>
      _ChatResponseSourcesDetailsTileState();
}

class _ChatResponseSourcesDetailsTileState
    extends State<_ChatResponseSourcesDetailsTile> {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded = _detailsInitiallyOpen(widget.extensionContext.element);
  }

  @override
  Widget build(BuildContext context) {
    final ctx = widget.extensionContext;
    final childList = ctx.builtChildrenMap!;
    final children = childList.values;

    final html.Element? detailsEl = ctx.element;
    final summaryPlain = _summaryPlainText(detailsEl);
    final sourceCount = _countSourcesInBody(detailsEl);
    final headerLabel =
        _expanded ? summaryPlain : '$summaryPlain ($sourceCount)';

    TextStyle? titleStyle;
    if (childList.keys.isNotEmpty && childList.keys.first.name == 'summary') {
      titleStyle = childList.keys.first.style.generateTextStyle();
    }

    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final panelBg = dark
        ? ChatImmersivePalette.darkRaised
        : theme.colorScheme.surfaceContainerHigh;
    final outline =
        dark ? ChatImmersivePalette.darkBorder : theme.colorScheme.outline;

    final effectiveStyle = titleStyle ??
        TextStyle(
          fontSize: 13.5,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.2,
          height: 1.25,
          color: dark
              ? ChatImmersivePalette.darkMuted
              : theme.colorScheme.onSurfaceVariant,
        );

    final iconColor = effectiveStyle.color;

    final bodySpans = childList.keys.isNotEmpty &&
            childList.keys.first.name == 'summary'
        ? children.skip(1).toList()
        : children.toList();

    return ClipRRect(
      key: AnchorKey.of(ctx.parser.key, ctx.styledElement!),
      borderRadius: BorderRadius.circular(8),
      child: Material(
          color: panelBg,
          shape: RoundedRectangleBorder(
            side: BorderSide(color: outline),
            borderRadius: BorderRadius.circular(8),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              InkWell(
                onTap: () => setState(() => _expanded = !_expanded),
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Text(
                          childList.keys.isNotEmpty &&
                                  childList.keys.first.name == 'summary'
                              ? headerLabel
                              : 'Details',
                          style: effectiveStyle,
                        ),
                      ),
                      Icon(
                        _expanded
                            ? Icons.expand_less
                            : Icons.expand_more,
                        size: 20,
                        color: iconColor,
                      ),
                    ],
                  ),
                ),
              ),
              if (_expanded)
                CssBoxWidget.withInlineSpanChildren(
                  children: bodySpans,
                  style: ctx.styledElement!.style,
                ),
            ],
          ),
        ),
    );
  }
}
