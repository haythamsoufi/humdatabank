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
import 'translation_entry_ui.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

class TranslationManagementScreen extends StatefulWidget {
  const TranslationManagementScreen({super.key});

  @override
  State<TranslationManagementScreen> createState() =>
      _TranslationManagementScreenState();
}

class _TranslationManagementScreenState extends State<TranslationManagementScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.translationManagement;

  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _sourceFilterController = TextEditingController();
  final FocusNode _sourceFilterFocusNode = FocusNode();
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
    _sourceFilterController.dispose();
    _sourceFilterFocusNode.dispose();
    super.dispose();
  }

  void _applyFilters() {
    final provider =
        Provider.of<TranslationManagementProvider>(context, listen: false);
    final sourceTrimmed = _sourceFilterController.text.trim();
    provider.loadTranslations(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      languageFilter: _selectedLanguageFilter,
      statusFilter: _selectedStatusFilter,
      sourceFilter: sourceTrimmed.isNotEmpty ? sourceTrimmed : null,
    );
  }

  void _clearFilters() {
    setState(() {
      _searchQuery = '';
      _searchController.clear();
      _sourceFilterController.clear();
      _selectedLanguageFilter = null;
      _selectedStatusFilter = null;
    });
    Provider.of<TranslationManagementProvider>(context, listen: false)
        .loadTranslations();
  }

  Future<void> _openFiltersBottomSheet() async {
    final provider =
        Provider.of<TranslationManagementProvider>(context, listen: false);
    await provider.ensureTranslationSourcesLoaded();
    if (!mounted) return;
    final loc = AppLocalizations.of(context)!;
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (sheetContext, setModalState) {
        final theme = Theme.of(sheetContext);
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
              Builder(
                builder: (sheetCtx) {
                  final paths = Provider.of<TranslationManagementProvider>(
                    sheetCtx,
                    listen: false,
                  ).translationSourceOptions;
                  return _TranslationSourcePathField(
                    controller: _sourceFilterController,
                    focusNode: _sourceFilterFocusNode,
                    allPaths: paths,
                    onFieldChanged: () {
                      setState(() {});
                      setModalState(() {});
                    },
                  );
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String?>(
                initialValue: _selectedLanguageFilter,
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
            tooltip: localizations.adminFilters,
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
                      label: Text(AppLocalizations.of(context)!.retry),
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
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              itemCount: provider.translations.length +
                  (provider.hasMore ? 1 : 0),
              itemBuilder: (context, index) {
                if (index >= provider.translations.length) {
                  return Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Center(
                      child: provider.isLoadingMore
                          ? CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(
                                Color(AppConstants.ifrcRed),
                              ),
                            )
                          : TextButton(
                              onPressed: () => provider.loadMore(),
                              child: Text(localizations.sessionLogsLoadMore),
                            ),
                    ),
                  );
                }
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
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () {
                      Navigator.of(context).pushNamed(
                        AppRoutes.translationEntryDetail,
                        arguments:
                            Map<String, dynamic>.from(translation),
                      );
                    },
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 14,
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.center,
                        children: [
                          Expanded(
                            child: Text(
                              TranslationEntryUi.msgid(translation),
                              maxLines: 3,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                                color: context.textColor,
                              ),
                            ),
                          ),
                          Icon(
                            Icons.chevron_right,
                            color: context.iconColor,
                          ),
                        ],
                      ),
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

/// Inline path list under the text field — [RawAutocomplete] uses an [Overlay]
/// that conflicts with [showModalBottomSheet] + [SingleChildScrollView]
/// (scroll/tap closes options immediately).
class _TranslationSourcePathField extends StatefulWidget {
  const _TranslationSourcePathField({
    required this.controller,
    required this.focusNode,
    required this.allPaths,
    required this.onFieldChanged,
  });

  final TextEditingController controller;
  final FocusNode focusNode;
  final List<String> allPaths;
  final VoidCallback onFieldChanged;

  @override
  State<_TranslationSourcePathField> createState() =>
      _TranslationSourcePathFieldState();
}

class _TranslationSourcePathFieldState extends State<_TranslationSourcePathField> {
  /// After user scrolls the path list, we unfocus to hide the keyboard but keep
  /// the list visible (it would otherwise disappear because it was tied to focus).
  bool _keepListOpenWithoutFocus = false;

  void _repaint() {
    if (mounted) setState(() {});
  }

  void _onFocusChanged() {
    if (widget.focusNode.hasFocus) {
      _keepListOpenWithoutFocus = false;
    }
    _repaint();
  }

  @override
  void initState() {
    super.initState();
    widget.focusNode.addListener(_onFocusChanged);
    widget.controller.addListener(_repaint);
  }

  @override
  void didUpdateWidget(covariant _TranslationSourcePathField oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusNode != widget.focusNode) {
      oldWidget.focusNode.removeListener(_onFocusChanged);
      widget.focusNode.addListener(_onFocusChanged);
    }
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_repaint);
      widget.controller.addListener(_repaint);
    }
  }

  @override
  void dispose() {
    widget.focusNode.removeListener(_onFocusChanged);
    widget.controller.removeListener(_repaint);
    super.dispose();
  }

  List<String> _filtered() {
    final q = widget.controller.text.trim().toLowerCase();
    final all = widget.allPaths;
    if (q.isEmpty) {
      if (all.length <= 150) return List<String>.from(all);
      return all.sublist(0, 150);
    }
    return all.where((s) => s.toLowerCase().contains(q)).take(150).toList();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final filtered = _filtered();
    final showList =
        widget.focusNode.hasFocus || _keepListOpenWithoutFocus;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        TextField(
          controller: widget.controller,
          focusNode: widget.focusNode,
          style: theme.textTheme.bodyLarge,
          decoration: InputDecoration(
            labelText: AppLocalizations.of(context)!.translationFilterSource,
            hintText: AppLocalizations.of(context)!.translationFilterSourceHint,
            labelStyle: TextStyle(color: context.textSecondaryColor),
            prefixIcon: Icon(Icons.folder_outlined, color: context.iconColor),
            suffixIcon: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Icon(
                    Icons.arrow_drop_down,
                    color: context.iconColor.withValues(alpha: 0.75),
                  ),
                ),
                if (widget.controller.text.isNotEmpty)
                  IconButton(
                    icon: Icon(Icons.clear, color: context.iconColor),
                    onPressed: () {
                      widget.controller.clear();
                      widget.onFieldChanged();
                      _repaint();
                    },
                  ),
              ],
            ),
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
          onChanged: (_) {
            widget.onFieldChanged();
            _repaint();
          },
        ),
        if (showList) ...[
          const SizedBox(height: 8),
          Material(
            elevation: 2,
            borderRadius: BorderRadius.circular(8),
            clipBehavior: Clip.antiAlias,
            color: theme.colorScheme.surfaceContainerHighest.withValues(
              alpha: 0.65,
            ),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 240),
              child: NotificationListener<ScrollNotification>(
                onNotification: (ScrollNotification n) {
                  if (n is ScrollStartNotification) {
                    if (widget.focusNode.hasFocus) {
                      widget.focusNode.unfocus();
                      _keepListOpenWithoutFocus = true;
                      widget.onFieldChanged();
                      _repaint();
                    }
                  }
                  // Keep drags on the list from scrolling the sheet behind it.
                  return true;
                },
                child: filtered.isEmpty
                    ? Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          'No matching paths',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: context.textSecondaryColor,
                          ),
                        ),
                      )
                    : ListView.separated(
                        primary: false,
                        physics: const ClampingScrollPhysics(),
                        itemCount: filtered.length,
                        separatorBuilder: (_, _) => Divider(
                          height: 1,
                          thickness: 1,
                          color: context.borderColor.withValues(alpha: 0.35),
                        ),
                        itemBuilder: (context, i) {
                          final opt = filtered[i];
                          return ListTile(
                            dense: true,
                            visualDensity: VisualDensity.compact,
                            contentPadding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 2,
                            ),
                            minVerticalPadding: 0,
                            title: Text(
                              opt,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            onTap: () {
                              widget.controller.text = opt;
                              _keepListOpenWithoutFocus = false;
                              widget.focusNode.unfocus();
                              widget.onFieldChanged();
                              _repaint();
                            },
                          );
                        },
                      ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}
