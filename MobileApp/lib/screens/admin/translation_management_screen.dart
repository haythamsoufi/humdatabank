import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/translation_management_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
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
        Provider.of<TranslationManagementProvider>(context, listen: false);
    provider.loadTranslations(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      languageFilter: _selectedLanguageFilter,
      statusFilter: _selectedStatusFilter,
    );
  }

  void _clearFilters() {
    setState(() {
      _searchQuery = '';
      _searchController.clear();
      _selectedLanguageFilter = null;
      _selectedStatusFilter = null;
    });
    Provider.of<TranslationManagementProvider>(context, listen: false)
        .loadTranslations();
  }

  Future<void> _openFiltersBottomSheet() async {
    final loc = AppLocalizations.of(context)!;
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (sheetContext, setModalState) {
        final theme = Theme.of(sheetContext);
        return AdminFilterPanel(
          title: loc.sessionLogsFilters,
          surfaceCard: false,
          actions: AdminFilterPanelActions(
            applyLabel: loc.sessionLogsApply,
            clearLabel: loc.sessionLogsClear,
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
                  labelText: loc.searchTranslations,
                  labelStyle: TextStyle(color: context.textSecondaryColor),
                  prefixIcon: Icon(Icons.search, color: context.iconColor),
                  suffixIcon: _searchQuery.isNotEmpty
                      ? IconButton(
                          icon: Icon(Icons.clear, color: context.iconColor),
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
                onChanged: (v) {
                  setState(() => _searchQuery = v);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                value: _selectedLanguageFilter,
                isExpanded: true,
                decoration: InputDecoration(
                  labelText: loc.language,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                  ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                  isDense: true,
                ),
                items: const [
                  DropdownMenuItem<String?>(
                    value: null,
                    child: Text(
                      'All Languages',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'en',
                    child: Text(
                      'English',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'fr',
                    child: Text(
                      'French',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'es',
                    child: Text(
                      'Spanish',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'ar',
                    child: Text(
                      'Arabic',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  setState(() => _selectedLanguageFilter = value);
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                value: _selectedStatusFilter,
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
                  const DropdownMenuItem<String?>(
                    value: 'pending',
                    child: Text(
                      'Pending',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String?>(
                    value: 'completed',
                    child: Text(
                      loc.completed,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const DropdownMenuItem<String?>(
                    value: 'review',
                    child: Text(
                      'Review',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  setState(() => _selectedStatusFilter = value);
                  setModalState(() {});
                },
              ),
            ],
          ),
        );
      },
    );
  }

  /// API JSON (`utilities.manage_translations`) uses `msgid`; HTML fallback uses `key`.
  String _translationMsgid(Map<String, dynamic> t) {
    final raw = t['msgid'] ?? t['key'];
    if (raw != null && raw.toString().trim().isNotEmpty) {
      return raw.toString();
    }
    return 'Unknown Key';
  }

  String? _translationSourceLine(Map<String, dynamic> t) {
    final s = t['source']?.toString();
    if (s == null || s.isEmpty || s == 'unknown') return null;
    return 'Source: $s';
  }

  List<Widget> _perLanguageTranslationBlocks(
    BuildContext context,
    Map<String, dynamic> t,
  ) {
    final nested = t['translations'];
    if (nested is Map) {
      final out = <Widget>[];
      final codes = nested.keys.map((k) => k.toString()).toList()..sort();
      for (final code in codes) {
        final langEntry = nested[code];
        if (langEntry is! Map) continue;
        final text = langEntry['text']?.toString() ?? '';
        final name =
            langEntry['language_name']?.toString() ?? code.toUpperCase();
        out.add(const SizedBox(height: 8));
        out.add(Text(
          name,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.w500,
            color: context.navyTextColor,
          ),
        ));
        out.add(const SizedBox(height: 4));
        out.add(Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: context.subtleSurfaceColor,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            text.isEmpty ? '—' : text,
            style: TextStyle(
              fontSize: 14,
              color: context.textColor,
            ),
          ),
        ));
      }
      return out;
    }

    final legacy = t['value']?.toString();
    if (legacy != null && legacy.isNotEmpty) {
      return [
        if (t['language'] != null) ...[
          const SizedBox(height: 8),
          Text(
            'Language: ${t['language']}',
            style: TextStyle(
              fontSize: 14,
              color: context.textSecondaryColor,
            ),
          ),
        ],
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: context.subtleSurfaceColor,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(
            legacy,
            style: TextStyle(
              fontSize: 14,
              color: context.textColor,
            ),
          ),
        ),
      ];
    }
    return [];
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    final chatbot = context.watch<AuthProvider>().user?.chatbotEnabled ?? false;
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.translationManagement,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: localizations.sessionLogsFilters,
            onPressed: _openFiltersBottomSheet,
          ),
        ],
      ),
      body: Consumer<TranslationManagementProvider>(
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
            onRefresh: () async => _applyFilters(),
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
                          _translationMsgid(translation),
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                            color: context.textColor,
                          ),
                        ),
                        if (_translationSourceLine(translation) !=
                            null) ...[
                          const SizedBox(height: 6),
                          Text(
                            _translationSourceLine(translation)!,
                            style: TextStyle(
                              fontSize: 12,
                              color: context.textSecondaryColor,
                            ),
                          ),
                        ],
                        ..._perLanguageTranslationBlocks(
                          context,
                          translation,
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
