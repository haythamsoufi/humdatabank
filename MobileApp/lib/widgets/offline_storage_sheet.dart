import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../services/assignment_offline_bundle_service.dart';
import '../theme/grouped_sheet_style.dart';

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
  List<OfflinePackageSummary>? _packages;
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
    final packages = await _service.listPackages();
    if (mounted) setState(() => _packages = packages);
  }

  Future<void> _remove(OfflinePackageSummary package) async {
    await _service.removePackage(package);
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
    final packages = _packages;
    final total = packages?.fold<int>(0, (sum, c) => sum + c.sizeBytes) ?? 0;

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
                          style: GroupedSheetStyle.title(context),
                        ),
                        Text(
                          packages == null || packages.isEmpty
                              ? loc.offlineStorageSubtitle
                              : '${loc.offlineStorageSubtitle} · ${formatOfflineCopySize(total)}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (packages != null && packages.isNotEmpty)
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
            Divider(height: 1, color: GroupedSheetStyle.hairline(context)),
            if (packages == null)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (packages.isEmpty)
              Padding(
                padding: const EdgeInsets.all(32),
                child: Center(child: Text(loc.offlineStorageEmpty)),
              )
            else
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                  itemCount: packages.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 8),
                  itemBuilder: (context, i) {
                    final g = packages[i];
                    final newest = g.savedAt;
                    return Material(
                      color: GroupedSheetStyle.card(context),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(
                          GroupedSheetStyle.cardRadius,
                        ),
                        side: BorderSide(
                          color: GroupedSheetStyle.hairline(context),
                        ),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: ListTile(
                        title: Text(
                          (g.title != null && g.title!.isNotEmpty)
                              ? g.title!
                              : '#${g.assignmentIds.isEmpty ? g.key : g.assignmentIds.first}',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodyLarge?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: GroupedSheetStyle.titleColor(context),
                          ),
                        ),
                        subtitle: Text(
                          [
                            '${loc.offlineStorageCopies}: ${g.assignmentIds.length}',
                            formatOfflineCopySize(g.sizeBytes),
                            if (newest != null) _dateLabel(newest),
                          ].join(' · '),
                        ),
                        trailing: IconButton(
                          tooltip: loc.offlineStorageRemove,
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () => _remove(g),
                        ),
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
