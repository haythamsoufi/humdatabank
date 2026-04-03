import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/audit_trail_provider.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

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
      _loadAuditLogs();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _loadAuditLogs() {
    final provider = Provider.of<AuditTrailProvider>(context, listen: false);
    provider.loadAuditLogs(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      actionFilter: _selectedActionFilter,
      userFilter: _selectedUserFilter,
      dateFrom: _selectedDateFrom,
      dateTo: _selectedDateTo,
    );
  }

  Future<void> _selectDateFrom(BuildContext context) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _selectedDateFrom ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
    );
    if (picked != null && picked != _selectedDateFrom) {
      setState(() {
        _selectedDateFrom = picked;
      });
      _loadAuditLogs();
    }
  }

  Future<void> _selectDateTo(BuildContext context) async {
    final DateTime? picked = await showDatePicker(
      context: context,
      initialDate: _selectedDateTo ?? DateTime.now(),
      firstDate: _selectedDateFrom ?? DateTime(2020),
      lastDate: DateTime.now(),
    );
    if (picked != null && picked != _selectedDateTo) {
      setState(() {
        _selectedDateTo = picked;
      });
      _loadAuditLogs();
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.auditTrail,
      ),
      body: Container(
        color: theme.scaffoldBackgroundColor,
        child: Column(
          children: [
            // Search and Filters
            Container(
              padding: const EdgeInsets.all(16),
              color: theme.cardTheme.color,
              child: Column(
                children: [
                  TextField(
                    controller: _searchController,
                    decoration: InputDecoration(
                      hintText: localizations.searchAuditLogs,
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear),
                              onPressed: () {
                                setState(() {
                                  _searchQuery = '';
                                  _searchController.clear();
                                });
                              },
                            )
                          : null,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                    ),
                    onChanged: (value) {
                      setState(() {
                        _searchQuery = value;
                      });
                      _loadAuditLogs();
                    },
                  ),
                  const SizedBox(height: 12),
                  // Filters Row 1
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          value: _selectedActionFilter,
                          decoration: InputDecoration(
                            labelText: localizations.action,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 12,
                            ),
                            isDense: true,
                          ),
                          items: [
                            DropdownMenuItem<String>(
                              value: null,
                              child: Text(localizations.allActions),
                            ),
                            DropdownMenuItem<String>(
                              value: 'create',
                              child: Text(localizations.create),
                            ),
                            DropdownMenuItem<String>(
                              value: 'update',
                              child: Text(localizations.update),
                            ),
                            DropdownMenuItem<String>(
                              value: 'delete',
                              child: Text(localizations.delete),
                            ),
                            DropdownMenuItem<String>(
                              value: 'login',
                              child: Text(localizations.login),
                            ),
                            DropdownMenuItem<String>(
                              value: 'logout',
                              child: Text(localizations.logout),
                            ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedActionFilter = value;
                            });
                            _loadAuditLogs();
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          value: _selectedUserFilter,
                          decoration: InputDecoration(
                            labelText: localizations.user,
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 12,
                            ),
                            isDense: true,
                          ),
                          items: [
                            DropdownMenuItem<String>(
                              value: null,
                              child: Text(localizations.allUsers),
                            ),
                            // User list would be populated from API
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedUserFilter = value;
                            });
                            _loadAuditLogs();
                          },
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  // Date Range Filters
                  Row(
                    children: [
                      Expanded(
                        child: InkWell(
                          onTap: () => _selectDateFrom(context),
                          child: InputDecorator(
                            decoration: InputDecoration(
                              labelText: localizations.fromDate,
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 12,
                              ),
                              isDense: true,
                            ),
                            child: Text(
                              _selectedDateFrom != null
                                  ? '${_selectedDateFrom!.year}-${_selectedDateFrom!.month.toString().padLeft(2, '0')}-${_selectedDateFrom!.day.toString().padLeft(2, '0')}'
                                  : localizations.selectDate,
                              style: TextStyle(
                                color: _selectedDateFrom != null
                                    ? context.textColor
                                    : context.textSecondaryColor,
                              ),
                            ),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: InkWell(
                          onTap: () => _selectDateTo(context),
                          child: InputDecorator(
                            decoration: InputDecoration(
                              labelText: localizations.toDate,
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                              contentPadding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 12,
                              ),
                              isDense: true,
                            ),
                            child: Text(
                              _selectedDateTo != null
                                  ? '${_selectedDateTo!.year}-${_selectedDateTo!.month.toString().padLeft(2, '0')}-${_selectedDateTo!.day.toString().padLeft(2, '0')}'
                                  : localizations.selectDate,
                              style: TextStyle(
                                color: _selectedDateTo != null
                                    ? context.textColor
                                    : context.textSecondaryColor,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Audit Trail List
            Expanded(
              child: Consumer<AuditTrailProvider>(
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
                            AppLocalizations.of(context)!.loadingAuditLogs,
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
                                _loadAuditLogs();
                              },
                              icon: const Icon(Icons.refresh, size: 18),
                              label: Text(localizations.retry),
                              style: OutlinedButton.styleFrom(
                                foregroundColor:
                                    Color(AppConstants.ifrcRed),
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
                            'No audit logs found',
                            style: const TextStyle(
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
                    onRefresh: () async => _loadAuditLogs(),
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
                                          borderRadius:
                                              BorderRadius.circular(12),
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
            ),
          ],
        ),
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: -1,
        onTap: (index) {
          Navigator.of(context).popUntil((route) {
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }
}
