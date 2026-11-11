import 'package:flutter/material.dart';

import '../utils/ai_chat_html_tables.dart';
import '../utils/theme_extensions.dart';

/// Horizontally scrollable HTML table for AI chat (native Flutter, not flutter_html).
class AiChatHtmlTableView extends StatelessWidget {
  final AiChatHtmlTableData table;
  final void Function(String url, {String? linkText})? onLinkTap;

  /// Soft cap so a runaway model answer cannot freeze the chat scroll view.
  final int maxRows;

  const AiChatHtmlTableView({
    super.key,
    required this.table,
    this.onLinkTap,
    this.maxRows = 120,
  });

  @override
  Widget build(BuildContext context) {
    if (table.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final outline = cs.outline.withValues(alpha: theme.isDarkTheme ? 0.38 : 0.22);
    final headerBg = theme.isDarkTheme
        ? cs.surfaceContainerHighest
        : cs.surfaceContainerHigh;
    final linkColor = context.linkOnSurfaceColor;
    final bodyStyle = TextStyle(
      fontSize: 12.5,
      height: 1.35,
      color: cs.onSurface,
    );
    final headerStyle = bodyStyle.copyWith(
      fontWeight: FontWeight.w600,
      letterSpacing: -0.1,
    );
    final mutedStyle = TextStyle(
      fontSize: 12,
      color: cs.onSurfaceVariant,
    );

    final visibleRows = table.rows.take(maxRows).toList();
    final omitted = table.rows.length - visibleRows.length;

    Widget cellWidget(AiChatHtmlTableCell cell, {required bool header}) {
      final style = header ? headerStyle : bodyStyle;
      final href = cell.href?.trim();
      final text = Text(
        (href != null && href.isNotEmpty && cell.text.isEmpty) ? href : cell.text,
        style: (href != null && href.isNotEmpty && onLinkTap != null && !header)
            ? style.copyWith(
                color: linkColor,
                decoration: TextDecoration.underline,
                decorationColor: linkColor.withValues(alpha: 0.7),
                fontWeight: FontWeight.w500,
              )
            : style,
      );
      if (href != null && href.isNotEmpty && onLinkTap != null && !header) {
        return Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: () => onLinkTap!(href, linkText: cell.text),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
              child: text,
            ),
          ),
        );
      }
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
        child: text,
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: outline),
          ),
          clipBehavior: Clip.antiAlias,
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Table(
              border: TableBorder.symmetric(
                inside: BorderSide(color: outline, width: 0.5),
              ),
              defaultVerticalAlignment: TableCellVerticalAlignment.middle,
              children: [
                if (table.headers.isNotEmpty)
                  TableRow(
                    decoration: BoxDecoration(color: headerBg),
                    children: [
                      for (final h in table.headers)
                        cellWidget(h, header: true),
                    ],
                  ),
                for (final row in visibleRows)
                  TableRow(
                    children: [
                      for (final c in row) cellWidget(c, header: false),
                    ],
                  ),
              ],
            ),
          ),
        ),
        if (omitted > 0)
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Text('+$omitted more rows', style: mutedStyle),
          ),
      ],
    );
  }
}
