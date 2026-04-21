import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/document_management_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/document.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

class DocumentManagementScreen extends StatefulWidget {
  const DocumentManagementScreen({super.key});

  @override
  State<DocumentManagementScreen> createState() =>
      _DocumentManagementScreenState();
}

class _DocumentManagementScreenState extends State<DocumentManagementScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.documentManagement;

  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedStatusFilter;
  String? _selectedTypeFilter;

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
        Provider.of<DocumentManagementProvider>(context, listen: false);
    provider.loadDocuments(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      statusFilter: _selectedStatusFilter,
      typeFilter: _selectedTypeFilter,
    );
  }

  void _clearFilters() {
    setState(() {
      _searchQuery = '';
      _searchController.clear();
      _selectedStatusFilter = null;
      _selectedTypeFilter = null;
    });
    Provider.of<DocumentManagementProvider>(context, listen: false)
        .loadDocuments();
  }

  Future<void> _openFiltersBottomSheet() async {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
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
                style: theme.textTheme.bodyLarge,
                decoration: InputDecoration(
                  labelText: loc.searchDocuments,
                  hintStyle: TextStyle(color: sheetContext.textSecondaryColor),
                  prefixIcon:
                      Icon(Icons.search, color: sheetContext.iconColor),
                  suffixIcon: _searchQuery.isNotEmpty
                      ? IconButton(
                          icon: Icon(Icons.clear, color: sheetContext.iconColor),
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
                    borderSide: BorderSide(color: sheetContext.borderColor),
                  ),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(color: sheetContext.borderColor),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(
                      color: Color(AppConstants.ifrcRed),
                      width: 2,
                    ),
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
                initialValue: _selectedStatusFilter,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: loc.status,
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
                    child: Text(
                      loc.allStatus,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'approved',
                    child: Text(
                      loc.approved,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const DropdownMenuItem<String?>(
                    value: 'pending',
                    child: Text(
                      'Pending',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const DropdownMenuItem<String?>(
                    value: 'rejected',
                    child: Text(
                      'Rejected',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  setState(() => _selectedStatusFilter = value);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                initialValue: _selectedTypeFilter,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: loc.type,
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
                    child: Text(
                      loc.allTypes,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const DropdownMenuItem<String?>(
                    value: 'report',
                    child: Text(
                      'Report',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'publication',
                    child: Text(
                      loc.publication,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const DropdownMenuItem<String?>(
                    value: 'cover_image',
                    child: Text(
                      'Cover Image',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  setState(() => _selectedTypeFilter = value);
                  setModalState(() {});
                },
              ),
            ],
          ),
        );
      },
    );
  }

  void _openDocumentDetail(Document document) {
    Navigator.of(context).pushNamed(
      AppRoutes.documentDetail(document.id),
      arguments: document,
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
        title: localizations.documentManagement,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: localizations.adminFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: ColoredBox(
        color: theme.scaffoldBackgroundColor,
        child: Consumer<DocumentManagementProvider>(
          builder: (context, provider, child) {
            if (provider.isLoading && provider.documents.isEmpty) {
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
                      AppLocalizations.of(context)!.loadingDocuments,
                      style: TextStyle(
                        color: context.textSecondaryColor,
                        fontSize: 14,
                      ),
                    ),
                  ],
                ),
              );
            }

            if (provider.error != null && provider.documents.isEmpty) {
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

            if (provider.documents.isEmpty) {
              return Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.description_outlined,
                      size: 56,
                      color: context.textSecondaryColor,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      localizations.noDocumentsFound,
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        color: context.textColor,
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
                itemCount: provider.documents.length,
                itemBuilder: (context, index) {
                  final document = provider.documents[index];
                  return _DocumentCard(
                    document: document,
                    onTap: () => _openDocumentDetail(document),
                  );
                },
              ),
            );
          },
        ),
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

class _DocumentCard extends StatelessWidget {
  final Document document;
  final VoidCallback onTap;

  const _DocumentCard({
    required this.document,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 0,
      color: theme.cardTheme.color,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(
          color: context.borderColor,
          width: 1,
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      document.fileName ??
                          AppLocalizations.of(context)!.genericUntitledDocument,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                        color: context.textColor,
                      ),
                    ),
                  ),
                  if (document.status != null)
                    Container(
                      margin: const EdgeInsets.only(right: 8),
                      padding: const EdgeInsets.symmetric(
                        horizontal: 8,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: _getStatusColor(document.status!, context)
                            .withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        document.status!,
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: _getStatusColor(document.status!, context),
                        ),
                      ),
                    ),
                  Icon(
                    Icons.chevron_right,
                    color: context.textSecondaryColor,
                    size: 20,
                  ),
                ],
              ),
              if (document.countryName != null) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    Icon(Icons.location_on,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      document.countryName!,
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
              if (document.documentType != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.description,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      document.documentType!,
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
              if (document.language != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.language,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      document.language!,
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
              if (document.year != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.calendar_today,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      'Year: ${document.year}',
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
              if (document.uploadedByName != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.person,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      'Uploaded by: ${document.uploadedByName}',
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
              if (document.uploadedAt != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.access_time,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      _formatDate(document.uploadedAt!),
                      style: TextStyle(
                        fontSize: 12,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
              if (document.assignmentPeriod != null) ...[
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.date_range,
                        size: 16, color: context.textSecondaryColor),
                    const SizedBox(width: 4),
                    Text(
                      'Period: ${document.assignmentPeriod}',
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Color _getStatusColor(String status, BuildContext context) {
    switch (status.toLowerCase()) {
      case 'approved':
        return Colors.green;
      case 'pending':
        return Colors.orange;
      case 'rejected':
        return Colors.red;
      default:
        return context.textSecondaryColor;
    }
  }

  String _formatDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }
}
