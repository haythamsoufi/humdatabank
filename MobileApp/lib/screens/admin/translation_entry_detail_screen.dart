import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../providers/admin/translation_management_provider.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import 'translation_entry_ui.dart';

/// Full-screen view of one translation entry (msgid + per-locale strings).
class TranslationEntryDetailScreen extends StatelessWidget {
  const TranslationEntryDetailScreen({
    super.key,
    required this.entry,
  });

  final Map<String, dynamic> entry;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final msg = TranslationEntryUi.msgid(entry);
    final rawSource = entry['source']?.toString();
    final hasSource = rawSource != null &&
        rawSource.isNotEmpty &&
        rawSource != 'unknown';

    final bottomInset = MediaQuery.paddingOf(context).bottom;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.indicatorDetailDetails,
      ),
      body: SingleChildScrollView(
        padding: EdgeInsets.fromLTRB(
          16,
          16,
          16,
          16 + bottomInset + 32,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Message key',
              style: theme.textTheme.labelLarge?.copyWith(
                color: context.textSecondaryColor,
              ),
            ),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: context.subtleSurfaceColor,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: context.borderColor),
              ),
              child: SelectableText(
                msg,
                style: TextStyle(
                  fontSize: 15,
                  height: 1.45,
                  fontWeight: FontWeight.w500,
                  color: context.textColor,
                ),
              ),
            ),
            if (hasSource) ...[
              const SizedBox(height: 16),
              Text(
                'Source',
                style: theme.textTheme.labelLarge?.copyWith(
                  color: context.textSecondaryColor,
                ),
              ),
              const SizedBox(height: 6),
              SelectableText(
                rawSource,
                style: TextStyle(
                  fontSize: 13,
                  color: context.textSecondaryColor,
                ),
              ),
            ],
            const SizedBox(height: 20),
            Row(
              children: [
                Icon(
                  Icons.translate,
                  size: 20,
                  color: Color(AppConstants.ifrcRed),
                ),
                const SizedBox(width: 8),
                Text(
                  'Translated strings',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: context.textColor,
                  ),
                ),
              ],
            ),
            ...TranslationEntryUi.perLanguageSections(
              context,
              entry,
              allowedLocaleCodes:
                  Provider.of<TranslationManagementProvider>(
                context,
                listen: false,
              ).translationLocaleAllowlist,
            ),
          ],
        ),
      ),
    );
  }
}
