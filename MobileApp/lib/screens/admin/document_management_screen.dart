import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/document_management_provider.dart';
import '../../models/shared/document.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class DocumentManagementScreen extends StatefulWidget {
  const DocumentManagementScreen({super.key});

  @override
  State<DocumentManagementScreen> createState() =>
      _DocumentManagementScreenState();
}

class _DocumentManagementScreenState extends State<DocumentManagementScreen> {
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedStatusFilter;
  String? _selectedTypeFilter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDocuments();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _loadDocuments() {
    final provider =
        Provider.of<DocumentManagementProvider>(context, listen: false);
    provider.loadDocuments(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      statusFilter: _selectedStatusFilter,
      typeFilter: _selectedTypeFilter,
    );
  }

  void _showDocumentActions(BuildContext context, Document document) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;
    showModalBottomSheet(
      context: context,
      backgroundColor: theme.cardTheme.color,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              margin: const EdgeInsets.only(top: 12, bottom: 8),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: context.textSecondaryColor.withOpacity(0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            ListTile(
              leading:
                  Icon(Icons.edit, color: Color(AppConstants.ifrcRed)),
              title: Text(localizations.editDocument),
              onTap: () {
                Navigator.pop(context);
                Navigator.of(context).pushNamed(
                  AppRoutes.webview,
                  arguments: '/admin/documents/edit/${document.id}',
                );
              },
            ),
            ListTile(
              leading:
                  Icon(Icons.preview, color: Color(AppConstants.ifrcRed)),
              title: Text(localizations.previewDocument),
              onTap: () {
                Navigator.pop(context);
                Navigator.of(context).pushNamed(
                  AppRoutes.webview,
                  arguments: '/admin/documents/serve/${document.id}',
                );
              },
            ),
            if (document.fileName != null)
              ListTile(
                leading: Icon(Icons.download,
                    color: Color(AppConstants.ifrcRed)),
                title: Text(localizations.downloadDocument),
                onTap: () {
                  Navigator.pop(context);
                  Navigator.of(context).pushNamed(
                    AppRoutes.webview,
                    arguments: '/admin/documents/download/${document.id}',
                  );
                },
              ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.documentManagement,
        actions: [
          // Add actions if needed
        ],
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
                    style: theme.textTheme.bodyLarge,
                    decoration: InputDecoration(
                      hintText: localizations.searchDocuments,
                      hintStyle: TextStyle(color: context.textSecondaryColor),
                      prefixIcon: Icon(Icons.search, color: context.iconColor),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: Icon(Icons.clear, color: context.iconColor),
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
                        borderSide: BorderSide(color: context.borderColor),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide: BorderSide(color: context.borderColor),
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
                    onChanged: (value) {
                      setState(() {
                        _searchQuery = value;
                      });
                      _loadDocuments();
                    },
                  ),
                  const SizedBox(height: 12),
                  // Filters Row
                  Row(
                    children: [
                      Expanded(
                        flex: 1,
                        child: DropdownButtonFormField<String>(
                          value: _selectedStatusFilter,
                          isExpanded: true,
                          decoration: InputDecoration(
                            labelText: localizations.status,
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
                              child: Text(
                                localizations.allStatus,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'approved',
                              child: Text(
                                localizations.approved,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'pending',
                              child: Text(
                                'Pending',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'rejected',
                              child: Text(
                                'Rejected',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedStatusFilter = value;
                            });
                            _loadDocuments();
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 1,
                        child: DropdownButtonFormField<String>(
                          value: _selectedTypeFilter,
                          isExpanded: true,
                          decoration: InputDecoration(
                            labelText: localizations.type,
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
                              child: Text(
                                localizations.allTypes,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'report',
                              child: Text(
                                'Report',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'publication',
                              child: Text(
                                localizations.publication,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'cover_image',
                              child: Text(
                                'Cover Image',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedTypeFilter = value;
                            });
                            _loadDocuments();
                          },
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Documents List
            Expanded(
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
                            Icon(
                              Icons.error_outline,
                              size: 48,
                              color: const Color(AppConstants.errorColor),
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
                                _loadDocuments();
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
                    onRefresh: () async => _loadDocuments(),
                    color: Color(AppConstants.ifrcRed),
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: provider.documents.length,
                      itemBuilder: (context, index) {
                        final document = provider.documents[index];
                        return _DocumentCard(
                          document: document,
                          onTap: () => _showDocumentActions(context, document),
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
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'document_management_upload_button',
        onPressed: () {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: '/admin/documents/upload',
          );
        },
        backgroundColor: Color(AppConstants.ifrcRed),
        icon: const Icon(Icons.upload),
        label: Text(localizations.uploadDocument),
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
                      document.fileName ?? 'Untitled Document',
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
                            .withOpacity(0.1),
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
