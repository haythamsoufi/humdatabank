import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/admin/audit_trail_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/audit_trail_widget_config.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';

class AuditTrailScreen extends StatefulWidget {
  const AuditTrailScreen({super.key});

  @override
  State<AuditTrailScreen> createState() => _AuditTrailScreenState();
}

class _AuditTrailScreenState extends State<AuditTrailScreen> {
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedActionFilter;
  String? _selectedUserFilter;
  DateTime? _selectedDateFrom;
  DateTime? _selectedDateTo;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _applyFilters();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  static String _formatDate(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  void _applyFilters() {
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    provider.loadAuditLogs(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      actionFilter: _selectedActionFilter,
      userFilter: _selectedUserFilter,
      dateFrom: _selectedDateFrom,
      dateTo: _selectedDateTo,
    );
  }

  void _clearFilters() {
    setState(() {
      _searchQuery = '';
      _searchController.clear();
      _selectedActionFilter = null;
      _selectedUserFilter = null;
      _selectedDateFrom = null;
      _selectedDateTo = null;
    });
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    provider.loadAuditLogs();
  }

  Future<void> _openFiltersBottomSheet() async {
    final loc = AppLocalizations.of(context)!;
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
              TextField(
                controller: _searchController,
                decoration: InputDecoration(
                  labelText: loc.searchAuditLogs,
                  prefixIcon: const Icon(Icons.search),
                ),
                onChanged: (v) {
                  setState(() => _searchQuery = v);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String>(
                value: _selectedActionFilter,
                decoration: InputDecoration(labelText: loc.action),
                items: [
                  DropdownMenuItem(
                      value: null, child: Text(loc.allActions)),
                  DropdownMenuItem(
                      value: 'create', child: Text(loc.create)),
                  DropdownMenuItem(
                      value: 'update', child: Text(loc.update)),
                  DropdownMenuItem(
                      value: 'delete', child: Text(loc.delete)),
                  DropdownMenuItem(
                      value: 'login', child: Text(loc.login)),
                  DropdownMenuItem(
                      value: 'logout', child: Text(loc.logout)),
                ],
                onChanged: (v) {
                  setState(() => _selectedActionFilter = v);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String>(
                value: _selectedUserFilter,
                decoration: InputDecoration(labelText: loc.user),
                items: [
                  DropdownMenuItem(
                      value: null, child: Text(loc.allUsers)),
                  // User list populated from API
                ],
                onChanged: (v) {
                  setState(() => _selectedUserFilter = v);
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
              if (AuditTrailWidgetConfig.isSupported) ...[
                AdminFilterPanel.fieldGap,
                const AuditTrailWidgetConfig(),
              ],
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
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
            return const Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.history_outlined,
                    size: 56,
                    color: Color(AppConstants.textSecondary),
                  ),
                  SizedBox(height: 16),
                  Text(
                    'No audit logs found',
                    style: TextStyle(
                      fontSize: 18,
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
              itemCount: provider.auditLogs.length,
              itemBuilder: (context, index) {
                final log = provider.auditLogs[index];
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
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Text(
                                log['description']?.toString() ??
                                    localizations.noDescription,
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  color: context.textColor,
                                ),
                              ),
                            ),
                            if (log['action'] != null)
                              Container(
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 8,
                                  vertical: 4,
                                ),
                                decoration: BoxDecoration(
                                  color: context.navyBackgroundColor(
                                      opacity: 0.1),
                                  borderRadius: BorderRadius.circular(12),
                                ),
                                child: Text(
                                  log['action'].toString(),
                                  style: TextStyle(
                                    fontSize: 12,
                                    fontWeight: FontWeight.w500,
                                    color: context.navyTextColor,
                                  ),
                                ),
                              ),
                          ],
                        ),
                        if (log['user'] != null) ...[
                          const SizedBox(height: 8),
                          Text(
                            'User: ${log['user']}',
                            style: TextStyle(
                              fontSize: 14,
                              color: context.textSecondaryColor,
                            ),
                          ),
                        ],
                        if (log['timestamp'] != null) ...[
                          const SizedBox(height: 4),
                          Text(
                            'Time: ${log['timestamp']}',
                            style: TextStyle(
                              fontSize: 12,
                              color: context.textSecondaryColor,
                            ),
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
