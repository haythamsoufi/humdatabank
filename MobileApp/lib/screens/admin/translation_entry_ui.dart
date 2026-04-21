import 'package:flutter/material.dart';

import '../../l10n/app_localizations.dart';
import '../../utils/theme_extensions.dart';

/// Shared parsing and widgets for translation list/detail (mobile API + HTML fallback).
class TranslationEntryUi {
  TranslationEntryUi._();

  static String msgid(Map<String, dynamic> t) {
    final raw = t['msgid'] ?? t['key'];
    if (raw != null && raw.toString().trim().isNotEmpty) {
      return raw.toString();
    }
    return 'Unknown Key';
  }

  /// Per-locale blocks for the detail screen (selectable text).
  ///
  /// When [allowedLocaleCodes] is non-null, only those locales are shown (case-insensitive).
  /// Use the allowlist from API `meta.languages` so disabled Backoffice languages never appear.
  static List<Widget> perLanguageSections(
    BuildContext context,
    Map<String, dynamic> t, {
    Set<String>? allowedLocaleCodes,
  }) {
    final loc = AppLocalizations.of(context)!;
    final nested = t['translations'];
    if (nested is Map) {
      final out = <Widget>[];
      final codes = nested.keys.map((k) => k.toString()).toList()..sort();

      for (final code in codes) {
        final codeLower = code.toLowerCase();
        if (allowedLocaleCodes != null &&
            allowedLocaleCodes.isNotEmpty &&
            !allowedLocaleCodes.contains(codeLower)) {
          continue;
        }
        final langEntry = nested[code];
        String text;
        String name;
        if (langEntry is String) {
          text = langEntry;
          name = loc.languageDisplayNameForLocaleCode(code);
        } else if (langEntry is Map) {
          text = langEntry['text']?.toString() ?? '';
          name = langEntry['language_name']?.toString() ??
              loc.languageDisplayNameForLocaleCode(code);
        } else {
          continue;
        }

        out.add(const SizedBox(height: 12));
        out.add(Text(
          '$name ($code)',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: context.navyTextColor,
          ),
        ));
        out.add(const SizedBox(height: 6));
        Widget body = Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: context.subtleSurfaceColor,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: context.borderColor),
          ),
          child: SelectableText(
            text.isEmpty ? loc.emptyEmDash : text,
            textAlign: TextAlign.start,
            style: TextStyle(
              fontSize: 15,
              height: 1.4,
              color: context.textColor,
            ),
          ),
        );
        if (_isRtlLocale(code)) {
          body = Directionality(
            textDirection: TextDirection.rtl,
            child: body,
          );
        }
        out.add(body);
      }
      return out;
    }

    final legacy = t['value']?.toString();
    if (legacy != null && legacy.isNotEmpty) {
      return [
        if (t['language'] != null) ...[
          const SizedBox(height: 12),
          Text(
            loc.translationLanguageLabel(t['language'].toString()),
            style: TextStyle(
              fontSize: 14,
              color: context.textSecondaryColor,
            ),
          ),
        ],
        const SizedBox(height: 12),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: context.subtleSurfaceColor,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: context.borderColor),
          ),
          child: SelectableText(
            legacy,
            style: TextStyle(
              fontSize: 15,
              color: context.textColor,
            ),
          ),
        ),
      ];
    }
    return [];
  }

  /// Primary script is RTL (Arabic and common locale variants e.g. ar_EG).
  static bool _isRtlLocale(String code) {
    final base = code.toLowerCase().split(RegExp(r'[-_]')).first;
    return base == 'ar';
  }

}
