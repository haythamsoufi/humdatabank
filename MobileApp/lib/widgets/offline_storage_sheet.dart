import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../services/assignment_offline_bundle_service.dart';

String formatOfflineCopySize(int bytes) {
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

/// Lists the forms saved for offline use and lets the user free the space.
Future<void> showOfflineStorageSheet(BuildContext context) {
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (_) => const _OfflineStorageSheet(),
  );
}

class _OfflineStorageSheet extends StatefulWidget {
  const _OfflineStorageSheet();

  @override
  State<_OfflineStorageSheet> createState() => _OfflineStorageSheetState();
}

class _OfflineStorageSheetState extends State<_OfflineStorageSheet> {
  final _service = AssignmentOfflineBundleService();
  List<OfflineCopySummary>? _copies;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    final copies = await _service.listSavedCopies();
    if (mounted) setState(() => _copies = copies);
  }

  Future<void> _remove(OfflineCopySummary copy) async {
    await _service.deleteBundle(copy.assignmentId);
    await _reload();
  }

  Future<void> _removeAll() async {
    final loc = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        content: Text(loc.offlineStorageRemoveAllConfirm),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(loc.cancel),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(loc.offlineStorageRemoveAll),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _service.clearAll();
    await _reload();
  }

  String _dateLabel(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final copies = _copies;
    final total = copies?.fold<int>(0, (sum, c) => sum + c.sizeBytes) ?? 0;

    return SafeArea(
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.75,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 8, 8),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          loc.offlineStorageTitle,
                          style: theme.textTheme.titleMedium,
                        ),
                        Text(
                          copies == null || copies.isEmpty
                              ? loc.offlineStorageSubtitle
                              : '${loc.offlineStorageSubtitle} · ${formatOfflineCopySize(total)}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (copies != null && copies.isNotEmpty)
                    TextButton(
                      onPressed: _removeAll,
                      child: Text(loc.offlineStorageRemoveAll),
                    ),
                ],
              ),
            ),
            if (copies == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (copies.isEmpty)
              Padding(
                padding: const EdgeInsets.all(32),
                child: Center(child: Text(loc.offlineStorageEmpty)),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: copies.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final c = copies[i];
                    final title = (c.title != null && c.title!.isNotEmpty)
                        ? c.title!
                        : '#${c.assignmentId}';
                    return ListTile(
                      title: Text(title, maxLines: 2, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                        [
                          formatOfflineCopySize(c.sizeBytes),
                          if (c.savedAt != null) _dateLabel(c.savedAt!),
                        ].join(' · '),
                      ),
                      trailing: IconButton(
                        tooltip: loc.offlineStorageRemove,
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () => _remove(c),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
