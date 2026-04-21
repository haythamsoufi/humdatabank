import 'dart:io' show Platform;

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/app_localizations.dart';
import '../providers/admin/audit_trail_provider.dart';
import '../services/audit_trail_home_widget_sync.dart';
import '../services/audit_trail_widget_prefs.dart';
import '../utils/theme_extensions.dart';

class AuditTrailWidgetConfig extends StatefulWidget {
  const AuditTrailWidgetConfig({super.key});

  static bool get isSupported =>
      !kIsWeb && (Platform.isIOS || Platform.isAndroid);

  @override
  State<AuditTrailWidgetConfig> createState() => _AuditTrailWidgetConfigState();
}

class _AuditTrailWidgetConfigState extends State<AuditTrailWidgetConfig> {
  Set<String> _activityFilter = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      final f = await AuditTrailWidgetPrefs.getActivityTypeFilter();
      if (mounted) setState(() => _activityFilter = f);
    });
  }

  Future<void> _toggle(String type) async {
    setState(() {
      final next = Set<String>.from(_activityFilter);
      if (next.contains(type)) {
        next.remove(type);
      } else {
        next.add(type);
      }
      _activityFilter = next;
    });
    await AuditTrailWidgetPrefs.setActivityTypeFilter(_activityFilter);
    if (!mounted) return;
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    await syncAuditTrailToHomeWidget(provider.auditLogs);
  }

  Widget _chip(BuildContext context, String type, String label) {
    return FilterChip(
      label: Text(label),
      selected: _activityFilter.contains(type),
      onSelected: (_) => _toggle(type),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      showCheckmark: false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 16),
        Divider(height: 1, color: context.borderColor),
        const SizedBox(height: 12),
        Text(
          localizations.homeScreenWidgetTitle,
          style: TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 14,
            color: context.textColor,
          ),
        ),
        const SizedBox(height: 6),
        Text(
          localizations.auditWidgetActivityTypesHint,
          style: TextStyle(
            fontSize: 12,
            color: context.textSecondaryColor,
          ),
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _chip(context, 'create', localizations.create),
            _chip(context, 'update', localizations.update),
            _chip(context, 'delete', localizations.delete),
            _chip(context, 'login', localizations.login),
            _chip(context, 'logout', localizations.logout),
          ],
        ),
      ],
    );
  }
}
