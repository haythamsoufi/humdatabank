import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../services/assignment_offline_bundle_service.dart';

String formatOfflineCopySize(int bytes) {
  if (bytes < 1024) return '$bytes B';
  if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
  return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
}

/// Saved copies of one form template (one per assignment/entity).
class OfflineTemplateGroup {
  OfflineTemplateGroup({required this.templateId, required this.title});

  final int? templateId;
  final String title;
  final List<OfflineCopySummary> copies = [];

  int get sizeBytes => copies.fold(0, (sum, c) => sum + c.sizeBytes);
}

/// Groups copies by template (copies without a known template stand alone).
List<OfflineTemplateGroup> groupOfflineCopies(List<OfflineCopySummary> copies) {
  final groups = <String, OfflineTemplateGroup>{};
  for (final c in copies) {
    final key = c.templateId != null ? 't${c.templateId}' : 'a${c.assignmentId}';
    final title = (c.title != null && c.title!.isNotEmpty)
        ? c.title!
        : '#${c.assignmentId}';
    groups.putIfAbsent(
      key,
      () => OfflineTemplateGroup(templateId: c.templateId, title: title),
    ).copies.add(c);
  }
  return groups.values.toList();
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
  bool _autoDownload = false;

  @override
  void initState() {
    super.initState();
    _reload();
    _service.isAutoDownloadEnabled().then((v) {
      if (mounted) setState(() => _autoDownload = v);
    });
  }

  Future<void> _reload() async {
    final copies = await _service.listSavedCopies();
    if (mounted) setState(() => _copies = copies);
  }

  Future<void> _remove(OfflineTemplateGroup group) async {
    final id = group.templateId;
    if (id != null) {
      await _service.deleteBundlesForTemplate(id);
    } else {
      for (final c in group.copies) {
        await _service.deleteBundle(c.assignmentId);
      }
    }
    await _reload();
  }

  Future<void> _toggleAutoDownload(bool value) async {
    setState(() => _autoDownload = value);
    await _service.setAutoDownloadEnabled(value);
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
    final groups = groupOfflineCopies(copies ?? const []);

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
            SwitchListTile(
              value: _autoDownload,
              onChanged: _toggleAutoDownload,
              title: Text(loc.offlineStorageAutoDownload),
              subtitle: Text(loc.offlineStorageAutoDownloadHint),
            ),
            const Divider(height: 1),
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
                  itemCount: groups.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final g = groups[i];
                    final newest = g.copies
                        .map((c) => c.savedAt)
                        .whereType<DateTime>()
                        .fold<DateTime?>(
                          null,
                          (a, b) => a == null || b.isAfter(a) ? b : a,
                        );
                    return ListTile(
                      title: Text(
                        g.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      subtitle: Text(
                        [
                          '${loc.offlineStorageCopies}: ${g.copies.length}',
                          formatOfflineCopySize(g.sizeBytes),
                          if (newest != null) _dateLabel(newest),
                        ].join(' · '),
                      ),
                      trailing: IconButton(
                        tooltip: loc.offlineStorageRemove,
                        icon: const Icon(Icons.delete_outline),
                        onPressed: () => _remove(g),
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
