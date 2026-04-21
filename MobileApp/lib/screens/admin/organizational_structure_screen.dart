import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/organizational_structure_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

class OrganizationalStructureScreen extends StatefulWidget {
  const OrganizationalStructureScreen({super.key});

  @override
  State<OrganizationalStructureScreen> createState() =>
      _OrganizationalStructureScreenState();
}

class _OrganizationalStructureScreenState extends State<OrganizationalStructureScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.organizationalStructure;

  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedLevelFilter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _applyFilters();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _applyFilters() {
    final provider =
        Provider.of<OrganizationalStructureProvider>(context, listen: false);
    provider.loadOrganizations(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      levelFilter: _selectedLevelFilter,
    );
  }

  void _clearFilters() {
    setState(() {
      _searchQuery = '';
      _searchController.clear();
      _selectedLevelFilter = null;
    });
    Provider.of<OrganizationalStructureProvider>(context, listen: false)
        .loadOrganizations();
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
                  labelText: loc.searchOrganizations,
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: _searchQuery.isNotEmpty
                      ? IconButton(
                          icon: const Icon(Icons.clear),
                          onPressed: () {
                            setState(() {
                              _searchQuery = '';
                              _searchController.clear();
                            });
                            setModalState(() {});
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
                onChanged: (v) {
                  setState(() => _searchQuery = v);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                initialValue: _selectedLevelFilter,
                decoration: InputDecoration(
                  labelText: loc.entityType,
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
                  DropdownMenuItem<String?>(
                    value: null,
                    child: Text(loc.allTypes),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'countries',
                    child: Text(loc.countries),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'nss',
                    child: Text(loc.nationalSocieties),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'ns_structure',
                    child: Text(loc.nsStructure),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'secretariat',
                    child: Text(loc.secretariat),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'divisions',
                    child: Text(loc.divisions),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'departments',
                    child: Text(loc.departments),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'regions',
                    child: Text(loc.regionalOffices),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'clusters',
                    child: Text(loc.clusterOffices),
                  ),
                ],
                onChanged: (v) {
                  setState(() => _selectedLevelFilter = v);
                  setModalState(() {});
                },
              ),
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
        title: localizations.organizationalStructure,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: localizations.adminFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: Consumer<OrganizationalStructureProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading && provider.organizations.isEmpty) {
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
                    AppLocalizations.of(context)!.loadingOrganizations,
                    style: TextStyle(
                      color: Theme.of(context)
                          .colorScheme
                          .onSurface
                          .withValues(alpha: 0.6),
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.error != null &&
              provider.organizations.isEmpty) {
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
                        color: Theme.of(context)
                            .colorScheme
                            .onSurface
                            .withValues(alpha: 0.6),
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

          if (provider.organizations.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.account_tree_outlined,
                    size: 56,
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withValues(alpha: 0.5),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.noOrganizationsFound,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: Theme.of(context).colorScheme.onSurface,
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
              itemCount: provider.organizations.length,
              itemBuilder: (context, index) {
                final org = provider.organizations[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: BorderSide(
                      color: Theme.of(context).dividerColor,
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
                                org['name']?.toString() ??
                                    'Unknown Organization',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.w600,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onSurface,
                                ),
                              ),
                            ),
                            if (org['id'] != null)
                              IconButton(
                                icon: const Icon(Icons.edit, size: 18),
                                color: Theme.of(context)
                                    .colorScheme
                                    .primary,
                                onPressed: () {
                                  final entityId = org['id'] as int;
                                  final entityType =
                                      org['entityType'] as String?;
                                  final entityName =
                                      org['name'] as String?;
                                  Navigator.of(context).pushNamed(
                                    AppRoutes.editEntity(
                                        entityId, entityType),
                                    arguments: {
                                      'entityName': entityName,
                                      'entityType': entityType,
                                    },
                                  );
                                },
                                tooltip: 'Edit',
                                padding: EdgeInsets.zero,
                                constraints: const BoxConstraints(
                                  minWidth: 32,
                                  minHeight: 32,
                                ),
                              ),
                          ],
                        ),
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
