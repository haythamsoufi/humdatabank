import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../config/routes.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/admin/audit_trail_provider.dart';
import '../../providers/admin/manage_users_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';

class AuditTrailScreen extends StatefulWidget {
  const AuditTrailScreen({super.key});

  @override
  State<AuditTrailScreen> createState() => _AuditTrailScreenState();
}

class _AuditTrailScreenState extends State<AuditTrailScreen>
    with AdminScreenViewLoggingMixin {
  final TextEditingController _userEmailController = TextEditingController();
  /// Picked from directory dropdown; combined with [ _userEmailController ] in
  /// [_effectiveUserEmailForApi].
  String? _selectedUserEmail;
  String? _activityTypeFilter;
  DateTime? _selectedDateFrom;
  DateTime? _selectedDateTo;

  @override
  String get adminScreenViewRoutePath => AppRoutes.auditTrail;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<ManageUsersProvider>().loadUsers();
      _applyFilters();
    });
  }

  @override
  void dispose() {
    _userEmailController.dispose();
    super.dispose();
  }

  static String _formatDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  /// Prefer partial text when it diverges from the dropdown pick; otherwise
  /// directory email, then free-text email filter.
  String? _effectiveUserEmailForApi() {
    final text = _userEmailController.text.trim();
    final sel = _selectedUserEmail;
    if (text.isNotEmpty && sel != null && text != sel) {
      return text;
    }
    if (sel != null && sel.isNotEmpty) return sel;
    if (text.isNotEmpty) return text;
    return null;
  }

  void _applyFilters() {
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    provider.loadAuditLogs(
      userEmailContains: _effectiveUserEmailForApi(),
      activityTypeFilter: _activityTypeFilter,
      dateFrom: _selectedDateFrom,
      dateTo: _selectedDateTo,
    );
  }

  void _loadMore() {
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    provider.loadMoreAuditLogs(
      userEmailContains: _effectiveUserEmailForApi(),
      activityTypeFilter: _activityTypeFilter,
      dateFrom: _selectedDateFrom,
      dateTo: _selectedDateTo,
    );
  }

  void _clearFilters() {
    setState(() {
      _selectedUserEmail = null;
      _userEmailController.clear();
      _activityTypeFilter = null;
      _selectedDateFrom = null;
      _selectedDateTo = null;
    });
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    provider.loadAuditLogs();
  }

  Future<void> _openFiltersBottomSheet() async {
    final loc = AppLocalizations.of(context)!;
    final usersProv = context.read<ManageUsersProvider>();
    if (usersProv.users.isEmpty && !usersProv.isLoading) {
      await usersProv.loadUsers();
    }
    if (!mounted) return;
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (sheetContext, setModalState) {
        return AdminFilterPanel(
          title: loc.adminFilters,
          surfaceCard: false,
          actions: AdminFilterPanelActions(
            applyLabel: loc.adminFiltersApply,
            clearLabel: loc.adminFiltersClear,
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
              Consumer<ManageUsersProvider>(
                builder: (context, usersProv, _) {
                  if (usersProv.isLoading && usersProv.users.isEmpty) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: LinearProgressIndicator(
                        minHeight: 3,
                        color: Color(AppConstants.ifrcRed),
                        backgroundColor:
                            Theme.of(context).colorScheme.surfaceContainerHighest,
                      ),
                    );
                  }
                  if (usersProv.error != null && usersProv.users.isEmpty) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Text(
                        usersProv.error!,
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    );
                  }
                  if (usersProv.users.isEmpty) {
                    return const SizedBox.shrink();
                  }
                  final sorted = [...usersProv.users]..sort(
                      (a, b) => a.email.toLowerCase().compareTo(b.email.toLowerCase()),
                    );
                  final knownEmails = sorted.map((u) => u.email).toSet();
                  final dropdownValue = _selectedUserEmail != null &&
                          knownEmails.contains(_selectedUserEmail)
                      ? _selectedUserEmail
                      : null;
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      DropdownButtonFormField<String?>(
                        key: ValueKey<String?>(dropdownValue),
                        initialValue: dropdownValue,
                        isExpanded: true,
                        menuMaxHeight: 360,
                        decoration: InputDecoration(
                          labelText: loc.user,
                        ),
                        items: [
                          DropdownMenuItem<String?>(
                            value: null,
                            child: Text(loc.allUsers),
                          ),
                          ...sorted.map((u) {
                            final name = u.name?.trim();
                            final label = (name != null && name.isNotEmpty)
                                ? '$name (${u.email})'
                                : u.email;
                            return DropdownMenuItem<String?>(
                              value: u.email,
                              child: Text(
                                label,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            );
                          }),
                        ],
                        onChanged: (v) {
                          setState(() {
                            _selectedUserEmail = v;
                            if (v != null) {
                              _userEmailController.text = v;
                            } else {
                              _userEmailController.clear();
                            }
                          });
                          setModalState(() {});
                        },
                      ),
                      AdminFilterPanel.fieldGap,
                    ],
                  );
                },
              ),
              TextField(
                controller: _userEmailController,
                decoration: InputDecoration(
                  labelText: loc.loginLogsEmailHint,
                  hintText: loc.sessionLogsEmailHint,
                  prefixIcon: const Icon(Icons.person_search_outlined),
                ),
                keyboardType: TextInputType.emailAddress,
                autocorrect: false,
                onChanged: (_) => setModalState(() {}),
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                key: ValueKey<String?>(_activityTypeFilter),
                initialValue: _activityTypeFilter,
                decoration:
                    InputDecoration(labelText: loc.auditTrailActivityLabel),
                items: [
                  DropdownMenuItem<String?>(
                      value: null, child: Text(loc.allActions)),
                  DropdownMenuItem<String?>(
                    value: 'login',
                    child: Text(loc.loginLogsEventLogin),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'logout',
                    child: Text(loc.loginLogsEventLogout),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'page_view',
                    child: Text(loc.sessionLogsPageViews),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'password_change',
                    child: Text(loc.changePassword),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'profile_update',
                    child: Text(loc.profile),
                  ),
                ],
                onChanged: (v) {
                  setState(() => _activityTypeFilter = v);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              InkWell(
                onTap: () async {
                  final picked = await showDatePicker(
                    context: sheetContext,
                    initialDate: _selectedDateFrom ?? DateTime.now(),
                    firstDate: DateTime(2020),
                    lastDate: DateTime.now(),
                  );
                  if (picked != null && picked != _selectedDateFrom) {
                    setState(() => _selectedDateFrom = picked);
                    setModalState(() {});
                  }
                },
                child: InputDecorator(
                  decoration: InputDecoration(labelText: loc.fromDate),
                  child: Text(
                    _selectedDateFrom != null
                        ? _formatDate(_selectedDateFrom!)
                        : loc.selectDate,
                    style: TextStyle(
                      color: _selectedDateFrom != null
                          ? Theme.of(context).colorScheme.onSurface
                          : Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
              AdminFilterPanel.fieldGap,
              InkWell(
                onTap: () async {
                  final picked = await showDatePicker(
                    context: sheetContext,
                    initialDate: _selectedDateTo ?? DateTime.now(),
                    firstDate: _selectedDateFrom ?? DateTime(2020),
                    lastDate: DateTime.now(),
                  );
                  if (picked != null && picked != _selectedDateTo) {
                    setState(() => _selectedDateTo = picked);
                    setModalState(() {});
                  }
                },
                child: InputDecorator(
                  decoration: InputDecoration(labelText: loc.toDate),
                  child: Text(
                    _selectedDateTo != null
                        ? _formatDate(_selectedDateTo!)
                        : loc.selectDate,
                    style: TextStyle(
                      color: _selectedDateTo != null
                          ? Theme.of(context).colorScheme.onSurface
                          : Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  String _primaryLine(Map<String, dynamic> log, AppLocalizations loc) {
    final consistent = (log['consistent_description'] ?? '').toString().trim();
    if (consistent.isNotEmpty) return consistent;
    final desc = (log['description'] ?? '').toString().trim();
    if (desc.isNotEmpty) return desc;
    final at = (log['activity_type'] ?? log['action'] ?? '').toString();
    final ep = (log['endpoint'] ?? '').toString();
    if (at.isNotEmpty && ep.isNotEmpty) return '$at · $ep';
    if (at.isNotEmpty) return at;
    if (ep.isNotEmpty) return ep;
    return loc.noDescription;
  }

  String _humanizeActivityType(String? raw) {
    if (raw == null || raw.isEmpty) return '';
    const labels = <String, String>{
      'request': 'Back-office action',
      'backoffice_action': 'Back-office action',
      'admin_ai': 'AI admin',
      'admin_content': 'Content',
      'admin_embed': 'Embed',
      'admin_assignments': 'Assignments',
      'admin_organization': 'Organization',
      'admin_system': 'System',
      'admin_users': 'Users',
      'admin_forms': 'Forms',
      'admin_analytics': 'Analytics',
      'admin_utilities': 'Utilities',
      'admin_settings': 'Settings',
      'admin_plugin': 'Plugins',
      'admin_notifications': 'Notifications',
      'admin_monitoring': 'Monitoring',
      'admin_portal': 'Portal',
      'admin_other': 'Other',
    };
    return labels[raw] ?? raw.replaceAll('_', ' ');
  }

  String _formatTimestamp(String? iso, String localeName) {
    if (iso == null || iso.isEmpty) return '—';
    final dt = DateTime.tryParse(iso);
    if (dt == null) return iso;
    try {
      return DateFormat.yMMMd(localeName).add_Hm().format(dt.toLocal());
    } catch (_) {
      return iso;
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final localeName = Localizations.localeOf(context).toString();
    final chatbot = context.watch<AuthProvider>().user?.chatbotEnabled ?? false;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.auditTrail,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: localizations.adminFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: Consumer<AuditTrailProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading && provider.auditLogs.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(
                      Color(AppConstants.ifrcRed),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.loadingAuditLogs,
                    style: TextStyle(
                      color: context.textSecondaryColor,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.error != null && provider.auditLogs.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const Icon(
                      Icons.error_outline,
                      size: 48,
                      color: Color(AppConstants.errorColor),
                    ),
                    const SizedBox(height: 16),
                    Text(
                      provider.error!,
                      style: TextStyle(
                        color: context.textSecondaryColor,
                        fontSize: 14,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      onPressed: () {
                        provider.clearError();
                        _applyFilters();
                      },
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(localizations.retry),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Color(AppConstants.ifrcRed),
                        side: BorderSide(
                          color: Color(AppConstants.ifrcRed),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          }

          if (provider.auditLogs.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.history_outlined,
                    size: 56,
                    color: Color(AppConstants.textSecondary),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.auditTrailNoEntries,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                      color: Color(AppConstants.textColor),
                    ),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => _applyFilters(),
            color: Color(AppConstants.ifrcRed),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: (provider.totalCount > 0 ? 1 : 0) +
                  provider.auditLogs.length +
                  (provider.hasMore ? 1 : 0),
              itemBuilder: (context, index) {
                final headerRows = provider.totalCount > 0 ? 1 : 0;
                if (headerRows == 1 && index == 0) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      localizations.sessionLogsTotalCount(provider.totalCount),
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w600,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  );
                }

                final logIndex = index - headerRows;
                if (logIndex == provider.auditLogs.length) {
                  return _AuditTrailLoadMoreFooter(
                    provider: provider,
                    onLoadMore: _loadMore,
                  );
                }

                final log = provider.auditLogs[logIndex];
                final title = _primaryLine(log, localizations);
                final activityRaw =
                    (log['activity_type'] ?? log['action'])?.toString();
                final activityLabel = _humanizeActivityType(activityRaw);
                final userLine =
                    (log['user_display'] ?? log['user'] ?? '').toString();
                final userSubtitle =
                    (log['user_subtitle'] ?? '').toString().trim();
                final ts = _formatTimestamp(
                  log['timestamp']?.toString(),
                  localeName,
                );

                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: BorderSide(
                      color: context.borderColor,
                      width: 1,
                    ),
                  ),
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
                                title,
                                style: TextStyle(
                                  fontSize: 15,
                                  fontWeight: FontWeight.w600,
                                  color: context.textColor,
                                ),
                              ),
                            ),
                            if (activityRaw != null &&
                                activityRaw.isNotEmpty) ...[
                              const SizedBox(width: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 4,
                                ),
                                decoration: BoxDecoration(
                                  color: context.navyBackgroundColor(opacity: 0.1),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(
                                  activityLabel.isNotEmpty
                                      ? activityLabel
                                      : activityRaw,
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: context.navyTextColor,
                                  ),
                                ),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            Icon(
                              Icons.schedule,
                              size: 14,
                              color: context.textSecondaryColor,
                            ),
                            const SizedBox(width: 4),
                            Expanded(
                              child: Text(
                                ts,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: context.textSecondaryColor,
                                ),
                              ),
                            ),
                          ],
                        ),
                        if (userLine.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Icon(
                                Icons.person_outline,
                                size: 16,
                                color: context.textSecondaryColor,
                              ),
                              const SizedBox(width: 6),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      userLine,
                                      style: TextStyle(
                                        fontSize: 13,
                                        fontWeight: FontWeight.w500,
                                        color: context.textColor,
                                      ),
                                    ),
                                    if (userSubtitle.isNotEmpty)
                                      Text(
                                        userSubtitle,
                                        style: TextStyle(
                                          fontSize: 12,
                                          color: context.textSecondaryColor,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        chatbotEnabled: chatbot,
        onTap: (index) {
          Navigator.of(context).popUntil((route) {
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }
}

class _AuditTrailLoadMoreFooter extends StatelessWidget {
  const _AuditTrailLoadMoreFooter({
    required this.provider,
    required this.onLoadMore,
  });

  final AuditTrailProvider provider;
  final VoidCallback onLoadMore;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    if (provider.isLoadingMore) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 20),
        child: Center(
          child: SizedBox(
            width: 28,
            height: 28,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 24),
      child: OutlinedButton(
        onPressed: onLoadMore,
        child: Text(loc.sessionLogsLoadMore),
      ),
    );
  }
}
