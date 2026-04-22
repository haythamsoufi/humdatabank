import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/login_log_item.dart';
import '../../providers/admin/login_logs_provider.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

/// Login / logout / failed-login events (aligned with web `/admin/analytics/login-logs`).
class LoginLogsScreen extends StatefulWidget {
  const LoginLogsScreen({super.key});

  @override
  State<LoginLogsScreen> createState() => _LoginLogsScreenState();
}

class _LoginLogsScreenState extends State<LoginLogsScreen>
    with AdminScreenViewLoggingMixin {
  final _emailController = TextEditingController();
  final _ipController = TextEditingController();
  String? _eventType;
  bool _suspiciousOnly = false;
  DateTime? _dateFrom;
  DateTime? _dateTo;

  @override
  String get adminScreenViewRoutePath => AppRoutes.loginLogs;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<LoginLogsProvider>().refresh();
    });
  }

  @override
  void dispose() {
    _emailController.dispose();
    _ipController.dispose();
    super.dispose();
  }

  void _applyFilters() {
    final p = context.read<LoginLogsProvider>();
    p.setFilters(
      userEmail: _emailController.text,
      eventType: _eventType,
      ip: _ipController.text,
      suspiciousOnly: _suspiciousOnly,
      dateFrom: _dateFrom != null
          ? DateFormat('yyyy-MM-dd').format(_dateFrom!)
          : null,
      dateTo:
          _dateTo != null ? DateFormat('yyyy-MM-dd').format(_dateTo!) : null,
    );
    p.refresh();
  }

  void _clearFilters() {
    setState(() {
      _emailController.clear();
      _ipController.clear();
      _eventType = null;
      _suspiciousOnly = false;
      _dateFrom = null;
      _dateTo = null;
    });
    final p = context.read<LoginLogsProvider>();
    p.setFilters(
      userEmail: null,
      eventType: null,
      ip: null,
      suspiciousOnly: false,
      dateFrom: null,
      dateTo: null,
    );
    p.refresh();
  }

  Future<void> _pickDate(BuildContext context, bool isFrom) async {
    final initial = isFrom
        ? (_dateFrom ?? DateTime.now())
        : (_dateTo ?? DateTime.now());
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (isFrom) {
        _dateFrom = picked;
      } else {
        _dateTo = picked;
      }
    });
  }

  Future<void> _openFiltersBottomSheet() async {
    final loc = AppLocalizations.of(context)!;
    final dateFmtShort = DateFormat.yMMMd();
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (sheetContext, setModalState) {
        return AdminFilterPanel(
          title: loc.loginLogsFilters,
          surfaceCard: false,
          actions: AdminFilterPanelActions(
            applyLabel: loc.loginLogsApply,
            clearLabel: loc.loginLogsClear,
            onApply: () {
              _applyFilters();
              Navigator.of(sheetContext).pop();
            },
            onClear: () {
              _clearFilters();
              setModalState(() {});
              Navigator.of(sheetContext).pop();
            },
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextField(
                controller: _emailController,
                decoration: InputDecoration(
                  labelText: loc.email,
                  hintText: loc.loginLogsEmailHint,
                ),
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                key: ValueKey<String?>(_eventType),
                initialValue: _eventType,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: loc.loginLogsEventType,
                ),
                items: [
                  DropdownMenuItem<String?>(
                    value: null,
                    child: Text(loc.loginLogsEventAll),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'login_success',
                    child: Text(loc.loginLogsEventLogin),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'logout',
                    child: Text(loc.loginLogsEventLogout),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'login_failed',
                    child: Text(loc.loginLogsEventFailed),
                  ),
                ],
                onChanged: (v) {
                  setState(() => _eventType = v);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              TextField(
                controller: _ipController,
                decoration: InputDecoration(
                  labelText: loc.loginLogsIpLabel,
                ),
                autocorrect: false,
              ),
              AdminFilterPanel.fieldGap,
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () async {
                        await _pickDate(context, true);
                        if (mounted) setModalState(() {});
                      },
                      child: Text(
                        _dateFrom != null
                            ? '${loc.loginLogsDateFrom}: ${dateFmtShort.format(_dateFrom!)}'
                            : loc.loginLogsDateFrom,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () async {
                        await _pickDate(context, false);
                        if (mounted) setModalState(() {});
                      },
                      child: Text(
                        _dateTo != null
                            ? '${loc.loginLogsDateTo}: ${dateFmtShort.format(_dateTo!)}'
                            : loc.loginLogsDateTo,
                      ),
                    ),
                  ),
                ],
              ),
              AdminFilterPanel.fieldGap,
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                title: Text(loc.loginLogsSuspiciousOnly),
                value: _suspiciousOnly,
                onChanged: (v) {
                  setState(() => _suspiciousOnly = v);
                  setModalState(() {});
                },
              ),
            ],
          ),
        );
      },
    );
  }

  String _eventLabel(String code, AppLocalizations loc) {
    switch (code) {
      case 'login_success':
        return loc.loginLogsEventLogin;
      case 'logout':
        return loc.loginLogsEventLogout;
      case 'login_failed':
        return loc.loginLogsEventFailed;
      default:
        return code;
    }
  }

  Color _eventColor(BuildContext context, String eventType) {
    final scheme = Theme.of(context).colorScheme;
    switch (eventType) {
      case 'login_success':
        return scheme.tertiary;
      case 'logout':
        return scheme.primary;
      case 'login_failed':
        return scheme.error;
      default:
        return scheme.outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final provider = context.watch<LoginLogsProvider>();

    return Scaffold(
      appBar: AppAppBar(
        title: loc.loginLogsTitle,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: loc.loginLogsFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: Text(
              loc.loginLogsTotalCount(provider.total),
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () => provider.refresh(),
              child: _buildBody(context, provider, loc),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    LoginLogsProvider provider,
    AppLocalizations loc,
  ) {
    if (provider.isLoading && provider.items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.35,
            child: const Center(child: CircularProgressIndicator()),
        ),
        ],
      );
    }

    if (provider.error != null && provider.items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          Icon(Icons.lock_outline, size: 48, color: Theme.of(context).colorScheme.error),
          const SizedBox(height: 16),
          Text(
            provider.error!,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 24),
          Center(
            child: FilledButton.icon(
              onPressed: () => provider.refresh(),
              icon: const Icon(Icons.refresh),
              label: Text(loc.retry),
            ),
          ),
        ],
      );
    }

    if (provider.items.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(height: MediaQuery.of(context).size.height * 0.2),
          Center(child: Text(loc.loginLogsNoEntries)),
        ],
      );
    }

    final dateFmt = DateFormat.yMMMd().add_jm();

    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      itemCount: provider.items.length + (provider.hasMore ? 1 : 0),
      itemBuilder: (context, i) {
        if (i >= provider.items.length) {
          return Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Center(
              child: provider.isLoadingMore
                  ? const CircularProgressIndicator()
                  : TextButton(
                      onPressed: () => provider.loadMore(),
                      child: Text(loc.loginLogsLoadMore),
                    ),
            ),
          );
        }
        final log = provider.items[i];
        return _LogTile(
          log: log,
          dateFmt: dateFmt,
          eventLabel: _eventLabel(log.eventType, loc),
          eventColor: _eventColor(context, log.eventType),
          localizations: loc,
        );
      },
    );
  }
}

class _LogTile extends StatelessWidget {
  const _LogTile({
    required this.log,
    required this.dateFmt,
    required this.eventLabel,
    required this.eventColor,
    required this.localizations,
  });

  final LoginLogItem log;
  final DateFormat dateFmt;
  final String eventLabel;
  final Color eventColor;
  final AppLocalizations localizations;

  @override
  Widget build(BuildContext context) {
    final loc = localizations;
    DateTime? ts;
    try {
      ts = DateTime.parse(log.timestampIso);
    } catch (_) {}

    final hasName = log.userName != null && log.userName!.trim().isNotEmpty;
    final titleText = hasName
        ? log.userName!.trim()
        : (log.userEmail != null && log.userEmail!.isNotEmpty
            ? log.userEmail!
            : (log.emailAttempted.isNotEmpty
                ? log.emailAttempted
                : '—'));
    final dateText =
        ts != null ? dateFmt.format(ts.toLocal()) : log.timestampIso;
    final showEmailUnderDate =
        hasName && log.userEmail != null && log.userEmail!.isNotEmpty;

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    titleText,
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: eventColor.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    eventLabel,
                    style: TextStyle(
                      color: eventColor,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              dateText,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (showEmailUnderDate) ...[
              const SizedBox(height: 2),
              Text(
                log.userEmail!,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
            if (log.userEmail == null && log.emailAttempted.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Text(
                  loc.loginLogsUserNotResolved,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ),
            const SizedBox(height: 6),
            Text(
              log.ipAddress,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    fontFamily: 'monospace',
                  ),
            ),
            if (log.location != null && log.location!.trim().isNotEmpty)
              Text(
                log.location!,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
            if (log.deviceType != null && log.deviceType!.trim().isNotEmpty)
              Text(
                '${loc.loginLogsDevice}: ${log.deviceType}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            if (log.browser != null && log.browser!.trim().isNotEmpty)
              Text(
                '${loc.loginLogsBrowser}: ${log.browser}',
                style: Theme.of(context).textTheme.bodySmall,
              ),
            if (log.eventType == 'login_failed' &&
                (log.failureReasonDisplay != null &&
                    log.failureReasonDisplay!.trim().isNotEmpty))
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  log.failureReasonDisplay!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.error,
                      ),
                ),
              ),
            if (log.isSuspicious || log.failedAttemptsCount > 1)
              Padding(
                padding: const EdgeInsets.only(top: 6),
                child: Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: [
                    if (log.isSuspicious)
                      Chip(
                        label: Text(loc.loginLogsSuspiciousBadge),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    if (log.failedAttemptsCount > 1)
                      Chip(
                        label: Text(loc.loginLogsRecentFailures(log.failedAttemptsCount)),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
