import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../providers/admin/translation_management_provider.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../widgets/app_bar.dart';
import 'translation_entry_ui.dart';

/// Full-screen view of one translation entry (msgid + per-locale strings).
class TranslationEntryDetailScreen extends StatefulWidget {
  const TranslationEntryDetailScreen({
    super.key,
    required this.entry,
  });

  final Map<String, dynamic> entry;

  @override
  State<TranslationEntryDetailScreen> createState() =>
      _TranslationEntryDetailScreenState();
}

class _TranslationEntryDetailScreenState
    extends State<TranslationEntryDetailScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.translationEntryDetail;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final entry = widget.entry;
    final msg = TranslationEntryUi.msgid(entry);
    final rawSource = entry['source']?.toString();
    final hasSource = rawSource != null &&
        rawSource.isNotEmpty &&
        rawSource != 'unknown';

    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final accent = Color(AppConstants.ifrcRed);

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
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w600,
                color: context.textColor,
              ),
            ),
            const SizedBox(height: 8),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: context.subtleSurfaceColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: theme.colorScheme.outlineVariant.withValues(alpha: 0.45),
                ),
              ),
              child: SelectableText(
                msg,
                style: theme.textTheme.bodyLarge?.copyWith(
                  height: 1.45,
                  fontWeight: FontWeight.w500,
                  color: context.textColor,
                ),
              ),
            ),
            if (hasSource) ...[
              const SizedBox(height: 20),
              Text(
                'Source',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                  color: context.textColor,
                ),
              ),
              const SizedBox(height: 8),
              SelectableText(
                rawSource,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: context.textSecondaryColor,
                  height: 1.4,
                ),
              ),
            ],
            const SizedBox(height: 24),
            Row(
              children: [
                Icon(
                  Icons.translate,
                  size: 22,
                  color: accent,
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
            const SizedBox(height: 8),
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
