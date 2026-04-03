import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/resources_management_provider.dart';
import '../../models/shared/resource.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class ResourcesManagementScreen extends StatefulWidget {
  const ResourcesManagementScreen({super.key});

  @override
  State<ResourcesManagementScreen> createState() =>
      _ResourcesManagementScreenState();
}

class _ResourcesManagementScreenState extends State<ResourcesManagementScreen> {
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedCategoryFilter;
  String? _selectedLanguageFilter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadResources();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _loadResources() {
    final provider =
        Provider.of<ResourcesManagementProvider>(context, listen: false);
    provider.loadResources(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      categoryFilter: _selectedCategoryFilter,
      languageFilter: _selectedLanguageFilter,
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.manageResources,
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
                      hintText: localizations.searchResources,
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
                      _loadResources();
                    },
                  ),
                  const SizedBox(height: 12),
                  // Filters Row
                  Row(
                    children: [
                      Expanded(
                        flex: 1,
                        child: DropdownButtonFormField<String>(
                          value: _selectedCategoryFilter,
                          isExpanded: true,
                          decoration: InputDecoration(
                            labelText: localizations.category,
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
                                localizations.allCategories,
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
                              value: 'resource',
                              child: Text(
                                localizations.resource,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'document',
                              child: Text(
                                localizations.document,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedCategoryFilter = value;
                            });
                            _loadResources();
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 1,
                        child: DropdownButtonFormField<String>(
                          value: _selectedLanguageFilter,
                          isExpanded: true,
                          decoration: InputDecoration(
                            labelText: localizations.language,
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
                                'All Languages',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'en',
                              child: Text(
                                'English',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'fr',
                              child: Text(
                                'French',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'es',
                              child: Text(
                                'Spanish',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'ar',
                              child: Text(
                                'Arabic',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedLanguageFilter = value;
                            });
                            _loadResources();
                          },
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Resources List
            Expanded(
              child: Consumer<ResourcesManagementProvider>(
                builder: (context, provider, child) {
                  if (provider.isLoading && provider.resources.isEmpty) {
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
                            AppLocalizations.of(context)!.loadingResources,
                            style: TextStyle(
                              color: context.textSecondaryColor,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    );
                  }

                  if (provider.error != null && provider.resources.isEmpty) {
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
                                _loadResources();
                              },
                              icon: const Icon(Icons.refresh, size: 18),
                              label: const Text('Retry'),
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

                  if (provider.resources.isEmpty) {
                    return Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.folder_open_outlined,
                            size: 56,
                            color: context.textSecondaryColor,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            localizations.noResourcesFound,
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
                    onRefresh: () async => _loadResources(),
                    color: Color(AppConstants.ifrcRed),
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: provider.resources.length,
                      itemBuilder: (context, index) {
                        final resource = provider.resources[index];
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
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  resource.title ?? 'Untitled Resource',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                    color: context.textColor,
                                  ),
                                ),
                                if (resource.resourceType != null) ...[
                                  const SizedBox(height: 8),
                                  Text(
                                    'Type: ${resource.resourceType}',
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: context.textSecondaryColor,
                                    ),
                                  ),
                                ],
                                if (resource.publicationDate != null) ...[
                                  const SizedBox(height: 4),
                                  Text(
                                    'Published: ${_formatDate(resource.publicationDate!)}',
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
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'resources_management_add_button',
        onPressed: () {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: '/admin/resources/new',
          );
        },
        backgroundColor: Color(AppConstants.ifrcRed),
        icon: const Icon(Icons.add),
        label: const Text('New Resource'),
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

  String _formatDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
  }
}
