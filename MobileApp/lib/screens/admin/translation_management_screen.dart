import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/translation_management_provider.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class TranslationManagementScreen extends StatefulWidget {
  const TranslationManagementScreen({super.key});

  @override
  State<TranslationManagementScreen> createState() =>
      _TranslationManagementScreenState();
}

class _TranslationManagementScreenState
    extends State<TranslationManagementScreen> {
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedLanguageFilter;
  String? _selectedStatusFilter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadTranslations();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _loadTranslations() {
    final provider =
        Provider.of<TranslationManagementProvider>(context, listen: false);
    provider.loadTranslations(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      languageFilter: _selectedLanguageFilter,
      statusFilter: _selectedStatusFilter,
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.translationManagement,
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
                      hintText: localizations.searchTranslations,
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
                      _loadTranslations();
                    },
                  ),
                  const SizedBox(height: 12),
                  // Filters Row
                  Row(
                    children: [
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
                            _loadTranslations();
                          },
                        ),
                      ),
                      const SizedBox(width: 12),
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
                              value: 'pending',
                              child: Text(
                                'Pending',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'completed',
                              child: Text(
                                localizations.completed,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            DropdownMenuItem<String>(
                              value: 'review',
                              child: Text(
                                'Review',
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                          onChanged: (value) {
                            setState(() {
                              _selectedStatusFilter = value;
                            });
                            _loadTranslations();
                          },
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            // Translations List
            Expanded(
              child: Consumer<TranslationManagementProvider>(
                builder: (context, provider, child) {
                  if (provider.isLoading && provider.translations.isEmpty) {
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
                            AppLocalizations.of(context)!.loadingTranslations,
                            style: TextStyle(
                              color: context.textSecondaryColor,
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    );
                  }

                  if (provider.error != null && provider.translations.isEmpty) {
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
                                _loadTranslations();
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

                  if (provider.translations.isEmpty) {
                    return Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.translate_outlined,
                            size: 56,
                            color: context.textSecondaryColor,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            localizations.noTranslationsFound,
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
                    onRefresh: () async => _loadTranslations(),
                    color: Color(AppConstants.ifrcRed),
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: provider.translations.length,
                      itemBuilder: (context, index) {
                        final translation = provider.translations[index];
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
                                  translation['key']?.toString() ??
                                      'Unknown Key',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                    color: context.textColor,
                                  ),
                                ),
                                if (translation['language'] != null) ...[
                                  const SizedBox(height: 8),
                                  Text(
                                    'Language: ${translation['language']}',
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: context.textSecondaryColor,
                                    ),
                                  ),
                                ],
                                if (translation['value'] != null &&
                                    translation['value']
                                        .toString()
                                        .isNotEmpty) ...[
                                  const SizedBox(height: 8),
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: context.subtleSurfaceColor,
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      translation['value'].toString(),
                                      style: TextStyle(
                                        fontSize: 14,
                                        color: context.textColor,
                                      ),
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
        heroTag: 'translation_management_add_button',
        onPressed: () {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: '/admin/translations/manage/new',
          );
        },
        backgroundColor: Color(AppConstants.ifrcRed),
        icon: const Icon(Icons.add),
        label: const Text('New Translation'),
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
