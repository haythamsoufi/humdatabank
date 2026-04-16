import 'dart:math' show min;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../config/routes.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/unified_planning_document.dart';
import '../../models/shared/resource.dart';
import '../../providers/public/public_resources_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../utils/constants.dart';
import '../../utils/navigation_helper.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_navigation_drawer.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/ios_button.dart';

class ResourcesScreen extends StatefulWidget {
  const ResourcesScreen({super.key});

  @override
  State<ResourcesScreen> createState() => _ResourcesScreenState();
}

class _ResourcesScreenState extends State<ResourcesScreen> {
  final TextEditingController _searchController = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  bool _showSearch = false;
  String? _lastLanguage;

  @override
  void initState() {
    super.initState();
    _scrollController.addListener(_onScroll);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    if (_lastLanguage != language) {
      _lastLanguage = language;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        Provider.of<PublicResourcesProvider>(context, listen: false)
            .loadResources(locale: language, refresh: true);
      });
    }
  }

  @override
  void dispose() {
    _searchController.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  void _onScroll() {
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - 300) {
      Provider.of<PublicResourcesProvider>(context, listen: false).loadMore();
    }
  }

  void _applySearch(String query) {
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    Provider.of<PublicResourcesProvider>(context, listen: false).loadResources(
      search: query,
      locale: language,
      refresh: true,
    );
  }

  void _applyType(String? type) {
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    Provider.of<PublicResourcesProvider>(context, listen: false).loadResources(
      type: type,
      locale: language,
      refresh: true,
    );
  }

  bool _isStandaloneScreen(BuildContext context) {
    final route = ModalRoute.of(context);
    final routeName = route?.settings.name;
    if (routeName == AppRoutes.resources) return true;
    if (routeName == null || routeName == AppRoutes.dashboard) return false;
    return Navigator.of(context).canPop();
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isStandalone = _isStandaloneScreen(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.resources,
        leading: Builder(
          builder: (BuildContext scaffoldContext) {
            return IOSIconButton(
              icon: Icons.menu,
              onPressed: () => Scaffold.of(scaffoldContext).openDrawer(),
              tooltip: loc.navigation,
              semanticLabel: loc.navigation,
              semanticHint: loc.navigation,
            );
          },
        ),
        actions: [
          IconButton(
            icon: AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: Icon(
                _showSearch ? Icons.search_off : Icons.search,
                key: ValueKey(_showSearch),
              ),
            ),
            tooltip: _showSearch
                ? loc.resourcesCloseSearchTooltip
                : loc.resourcesSearchTooltip,
            onPressed: () {
              setState(() {
                _showSearch = !_showSearch;
                if (!_showSearch) {
                  _searchController.clear();
                  _applySearch('');
                }
              });
            },
          ),
        ],
      ),
      drawer: AppNavigationDrawer(
        activeScreen: ActiveDrawerScreen.resources,
        onShowCountriesSheet: () => _showCountriesSheet(context, theme),
      ),
      body: Consumer2<PublicResourcesProvider, LanguageProvider>(
        builder: (context, provider, languageProvider, _) {
          final language = languageProvider.currentLanguage;
          return Column(
            children: [
              // ── Search field ───────────────────────────────────────
              AnimatedSize(
                duration: const Duration(milliseconds: 220),
                curve: Curves.easeInOut,
                child: _showSearch
                    ? _SearchBar(
                        controller: _searchController,
                        onSubmitted: _applySearch,
                      )
                    : const SizedBox.shrink(),
              ),

              // ── Type filter chips ──────────────────────────────────
              const SizedBox(height: 8),
              _TypeFilterRow(
                selected: provider.selectedType,
                onSelected: _applyType,
              ),

              // ── Content area ───────────────────────────────────────
              Expanded(
                child: _buildBody(context, provider, loc, theme, language),
              ),
            ],
          );
        },
      ),
      bottomNavigationBar: isStandalone
          ? AppBottomNavigationBar(
              currentIndex: 2,
              onTap: (index) {
                NavigationHelper.popToMainThenOpenAiIfNeeded(context, index);
              },
            )
          : null,
    );
  }

  Widget _buildBody(
    BuildContext context,
    PublicResourcesProvider provider,
    AppLocalizations loc,
    ThemeData theme,
    String language,
  ) {
    // ── Shimmer skeleton while loading ─────────────────────────────
    if (provider.isLoading && provider.resources.isEmpty) {
      return const _ShimmerGrid();
    }

    // ── Error state ────────────────────────────────────────────────
    if (provider.error != null && provider.resources.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: const Color(AppConstants.errorColor).withValues(alpha: 0.1),
                  shape: BoxShape.circle,
                ),
                child: const Icon(
                  Icons.wifi_off_rounded,
                  size: 52,
                  color: Color(AppConstants.errorColor),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                provider.error!,
                style: TextStyle(
                  color: context.textSecondaryColor,
                  fontSize: 14,
                  height: 1.5,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 28),
              FilledButton.icon(
                onPressed: () {
                  provider.clearError();
                  provider.loadResources(locale: language, refresh: true);
                },
                icon: const Icon(Icons.refresh_rounded, size: 18),
                label: Text(loc.retry),
                style: FilledButton.styleFrom(
                  backgroundColor: Color(AppConstants.ifrcRed),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 24, vertical: 12),
                ),
              ),
            ],
          ),
        ),
      );
    }

    // ── Empty state (library only — unified planning section may still show) ─
    final unifiedDocs = provider.unifiedPlanningDocuments;
    final showUnifiedPlanningBlock = provider.unifiedPlanningLoading ||
        unifiedDocs.isNotEmpty ||
        provider.unifiedPlanningErrorCode != null;

    if (!provider.isLoading &&
        provider.resources.isEmpty &&
        !showUnifiedPlanningBlock) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.inventory_2_outlined,
              size: 72,
              color: context.textSecondaryColor.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 16),
            Text(
              loc.noResourcesFound,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.w700,
                color: context.textColor,
              ),
            ),
          ],
        ),
      );
    }

    // ── Scroll: unified planning + resource grid ───────────────────
    return RefreshIndicator(
      onRefresh: () => provider.loadResources(locale: language, refresh: true),
      color: Color(AppConstants.ifrcRed),
      child: CustomScrollView(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (showUnifiedPlanningBlock)
            SliverToBoxAdapter(
              child: _UnifiedPlanningSection(
                loc: loc,
                theme: theme,
                isLoading: provider.unifiedPlanningLoading,
                errorCode: provider.unifiedPlanningErrorCode,
                documents: unifiedDocs,
                onOpen: (url, title) => _openResource(context, url, title: title),
              ),
            ),
          if (provider.resources.isNotEmpty)
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
              sliver: SliverGrid(
                gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                  childAspectRatio: 0.66,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    if (index >= provider.resources.length) {
                      return const _ShimmerCard();
                    }
                    final res = provider.resources[index];
                    return _ResourceCard(
                      key: ValueKey(res.id),
                      resource: res,
                      index: index,
                      currentLanguage: language,
                      onOpen: (url) => _openResource(
                        context,
                        url,
                        title: res.title ?? loc.document,
                      ),
                    );
                  },
                  childCount:
                      provider.resources.length + (provider.isLoadingMore ? 2 : 0),
                ),
              ),
            )
          else if (!provider.isLoading && showUnifiedPlanningBlock)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(24, 8, 24, 8),
                child: Text(
                  loc.noResourcesFound,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: context.textSecondaryColor,
                    fontSize: 14,
                  ),
                ),
              ),
            ),
          const SliverToBoxAdapter(child: SizedBox(height: 24)),
        ],
      ),
    );
  }

  void _openResource(
    BuildContext context,
    String url, {
    String? title,
  }) {
    final resolvedTitle = title ?? AppLocalizations.of(context)!.document;
    // All resource file_url values come from /resources/download/<id>/<lang>
    // which streams the file (typically a PDF) via the backend.
    // Route directly to the in-app PDF viewer; it has an "Open in browser"
    // fallback in its own error state for any non-PDF content.
    Navigator.of(context).pushNamed(
      AppRoutes.pdfViewer,
      arguments: <String, String>{'url': url, 'title': resolvedTitle},
    );
  }

  void _showCountriesSheet(BuildContext context, ThemeData theme) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) {
        return Container(
          constraints: BoxConstraints(
              maxHeight: MediaQuery.of(context).size.height * 0.9),
          decoration: BoxDecoration(
            color: theme.scaffoldBackgroundColor,
            borderRadius:
                const BorderRadius.vertical(top: Radius.circular(20)),
          ),
          child: SafeArea(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  margin: const EdgeInsets.only(top: 12, bottom: 8),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: theme.dividerColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 24, vertical: 16),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        AppLocalizations.of(context)!.countries,
                        style: theme.textTheme.titleLarge
                            ?.copyWith(fontWeight: FontWeight.bold),
                      ),
                      IconButton(
                        icon: const Icon(Icons.close),
                        onPressed: () => Navigator.pop(sheetContext),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                const Expanded(child: CountriesWidget()),
              ],
            ),
          ),
        );
      },
    );
  }
}

// ── Unified planning (IFRC GO — client-side) ────────────────────────────────

class _UnifiedPlanningSection extends StatelessWidget {
  final AppLocalizations loc;
  final ThemeData theme;
  final bool isLoading;
  final String? errorCode;
  final List<UnifiedPlanningDocument> documents;
  final void Function(String url, String title) onOpen;

  const _UnifiedPlanningSection({
    required this.loc,
    required this.theme,
    required this.isLoading,
    required this.errorCode,
    required this.documents,
    required this.onOpen,
  });

  String? _errorMessage() {
    switch (errorCode) {
      case 'unified_error_config':
        return loc.unifiedPlanningErrorConfig;
      case 'unified_error_credentials':
        return loc.unifiedPlanningErrorCredentials;
      case 'unified_error_ifrc_auth':
        return loc.unifiedPlanningErrorIfrcAuth;
      case 'unified_error_ifrc':
        return loc.unifiedPlanningErrorIfrc;
      default:
        return null;
    }
  }

  @override
  Widget build(BuildContext context) {
    final err = _errorMessage();

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            loc.resourcesUnifiedPlanningSectionTitle,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w800,
              color: context.textColor,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            loc.resourcesUnifiedPlanningSectionSubtitle,
            style: theme.textTheme.bodySmall?.copyWith(
              color: context.textSecondaryColor,
              height: 1.35,
            ),
          ),
          const SizedBox(height: 12),
          if (isLoading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Center(
                child: SizedBox(
                  width: 28,
                  height: 28,
                  child: CircularProgressIndicator(strokeWidth: 2.5),
                ),
              ),
            )
          else if (err != null)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(AppConstants.errorColor).withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: const Color(AppConstants.errorColor).withValues(alpha: 0.25),
                ),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.info_outline_rounded,
                    size: 20,
                    color: Color(AppConstants.errorColor),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      err,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: context.textColor,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            )
          else if (documents.isEmpty)
            Text(
              loc.unifiedPlanningEmpty,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: context.textSecondaryColor,
              ),
            )
          else
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: documents.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final d = documents[i];
                final meta = <String>[
                  if (d.documentTypeLabel != null && d.documentTypeLabel!.isNotEmpty)
                    d.documentTypeLabel!,
                  if (d.countryName != null && d.countryName!.isNotEmpty)
                    d.countryName!,
                  if (d.year != null) '${d.year}',
                ].join(' · ');
                return ListTile(
                  contentPadding: const EdgeInsets.symmetric(vertical: 2),
                  leading: Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFB71C1C).withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.picture_as_pdf_rounded,
                      color: Color(0xFFB71C1C),
                      size: 22,
                    ),
                  ),
                  title: Text(
                    d.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  subtitle: meta.isEmpty
                      ? null
                      : Text(
                          meta,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: context.textSecondaryColor,
                          ),
                        ),
                  trailing: const Icon(Icons.chevron_right_rounded),
                  onTap: () => onOpen(d.url, d.title),
                );
              },
            ),
        ],
      ),
    );
  }
}

// ── Search bar ─────────────────────────────────────────────────────────────

class _SearchBar extends StatelessWidget {
  final TextEditingController controller;
  final ValueChanged<String> onSubmitted;

  const _SearchBar({required this.controller, required this.onSubmitted});

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 4),
      child: TextField(
        controller: controller,
        autofocus: true,
        textInputAction: TextInputAction.search,
        style: theme.textTheme.bodyLarge,
        decoration: InputDecoration(
          hintText: loc.searchResources,
          hintStyle: TextStyle(color: context.textSecondaryColor),
          prefixIcon: Icon(Icons.search_rounded, color: context.iconColor),
          suffixIcon: controller.text.isNotEmpty
              ? IconButton(
                  icon: Icon(Icons.clear_rounded, color: context.iconColor),
                  onPressed: () {
                    controller.clear();
                    onSubmitted('');
                  },
                )
              : null,
          filled: true,
          fillColor: context.dividerColor.withValues(alpha: 0.5),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide(
              color: Color(AppConstants.ifrcRed),
              width: 1.5,
            ),
          ),
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          isDense: true,
        ),
        onSubmitted: onSubmitted,
        onChanged: (_) => (context as Element).markNeedsBuild(),
      ),
    );
  }
}

// ── Type filter chips ──────────────────────────────────────────────────────

class _TypeFilterRow extends StatelessWidget {
  final String? selected;
  final ValueChanged<String?> onSelected;

  const _TypeFilterRow({required this.selected, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final filters = <String?, String>{
      null: loc.allCategories,
      'publication': loc.publication,
      'resource': loc.resource,
      'document': loc.document,
    };

    return SizedBox(
      height: 44,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 14),
        children: filters.entries.map((entry) {
          final isActive = entry.key == selected;
          return Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Center(
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                curve: Curves.easeInOut,
                decoration: BoxDecoration(
                  color: isActive
                      ? Color(AppConstants.ifrcRed)
                      : (isDark
                          ? Colors.white.withValues(alpha: 0.08)
                          : Colors.black.withValues(alpha: 0.06)),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: InkWell(
                  onTap: () => onSelected(entry.key),
                  borderRadius: BorderRadius.circular(20),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 7),
                    child: Text(
                      entry.value,
                      style: TextStyle(
                        color: isActive
                            ? Colors.white
                            : context.textSecondaryColor,
                        fontSize: 13,
                        fontWeight:
                            isActive ? FontWeight.w700 : FontWeight.w500,
                        height: 1.0,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}

// ── Resource card ──────────────────────────────────────────────────────────

class _ResourceCard extends StatefulWidget {
  final Resource resource;
  final int index;
  final ValueChanged<String> onOpen;

  /// The current UI language code (e.g. 'ar', 'en', 'fr').
  /// Used at tap time to pick the best available document language.
  final String currentLanguage;

  const _ResourceCard({
    super.key,
    required this.resource,
    required this.index,
    required this.onOpen,
    required this.currentLanguage,
  });

  @override
  State<_ResourceCard> createState() => _ResourceCardState();
}

class _ResourceCardState extends State<_ResourceCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pressController;
  late final Animation<double> _scale;
  bool _visible = false;

  // ── Helpers ────────────────────────────────────────────────────

  /// Resolve the best file URL for [resource] given [language].
  ///
  /// Priority: current UI language → English → first available language.
  /// Falls back to the pre-resolved [Resource.fileUrl] if [fileLanguages]
  /// is empty (older API responses that don't include the field yet).
  ///
  /// The download URL format is:  {base}/resources/download/{id}/{lang}
  /// We replace only the trailing language segment so the base URL
  /// (including host and scheme) is always preserved from the original.
  static String? _localizedFileUrl(Resource resource, String language) {
    if (resource.fileUrl == null) return null;

    // If server didn't return file_languages, keep the pre-resolved URL.
    if (resource.fileLanguages.isEmpty) return resource.fileUrl;

    final langs = resource.fileLanguages;
    final String resolvedLang;
    if (langs.contains(language)) {
      resolvedLang = language;
    } else if (langs.contains('en')) {
      resolvedLang = 'en';
    } else {
      resolvedLang = langs.first;
    }

    // Replace the trailing /{lang} segment in the existing URL.
    final url = resource.fileUrl!;
    final lastSlash = url.lastIndexOf('/');
    if (lastSlash < 0) return url;
    return '${url.substring(0, lastSlash)}/$resolvedLang';
  }

  static Color _accentForType(String? type) {
    switch (type) {
      case 'publication':
        return const Color(0xFF0D47A1);
      case 'document':
        return const Color(0xFF1B5E20);
      default:
        return const Color(0xFF4A148C);
    }
  }

  static List<Color> _gradientForType(String? type) {
    switch (type) {
      case 'publication':
        return [const Color(0xFF0D47A1), const Color(0xFF1976D2)];
      case 'document':
        return [const Color(0xFF1B5E20), const Color(0xFF388E3C)];
      default:
        return [const Color(0xFF4A148C), const Color(0xFF7B1FA2)];
    }
  }

  static IconData _iconForType(String? type) {
    switch (type) {
      case 'publication':
        return Icons.menu_book_rounded;
      case 'document':
        return Icons.description_rounded;
      default:
        return Icons.folder_rounded;
    }
  }

  String _formatDate(DateTime dt) {
    const m = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ];
    return '${m[dt.month - 1]} ${dt.year}';
  }

  @override
  void initState() {
    super.initState();
    _pressController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 90),
    );
    _scale = Tween<double>(begin: 1.0, end: 0.94).animate(
      CurvedAnimation(parent: _pressController, curve: Curves.easeInOut),
    );
    // Staggered entrance: cap delay so later items don't wait forever.
    final delay = Duration(
        milliseconds: min(widget.index, 7) * 65);
    Future.delayed(delay, () {
      if (mounted) setState(() => _visible = true);
    });
  }

  @override
  void dispose() {
    _pressController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final resource = widget.resource;
    final accent = _accentForType(resource.resourceType);
    final gradient = _gradientForType(resource.resourceType);
    final icon = _iconForType(resource.resourceType);
    final hasThumbnail =
        resource.thumbnailUrl != null && resource.thumbnailUrl!.isNotEmpty;
    final hasFile =
        resource.fileUrl != null && resource.fileUrl!.isNotEmpty;
    final typeLabel = resource.resourceType ?? loc.genericLowercaseResource;
    final title = resource.title ?? loc.genericUntitled;

    return AnimatedOpacity(
      opacity: _visible ? 1.0 : 0.0,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOut,
      child: AnimatedSlide(
        offset: _visible ? Offset.zero : const Offset(0, 0.08),
        duration: const Duration(milliseconds: 320),
        curve: Curves.easeOut,
        child: GestureDetector(
          onTapDown: (_) => _pressController.forward(),
          onTapUp: (_) {
            _pressController.reverse();
            if (hasFile) {
              final url = _localizedFileUrl(
                    widget.resource, widget.currentLanguage) ??
                  resource.fileUrl!;
              widget.onOpen(url);
            }
          },
          onTapCancel: () => _pressController.reverse(),
          child: AnimatedBuilder(
            animation: _scale,
            builder: (context, child) =>
                Transform.scale(scale: _scale.value, child: child),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  // ── Background image or gradient ─────────────────
                  if (hasThumbnail)
                    Image.network(
                      resource.thumbnailUrl!,
                      fit: BoxFit.cover,
                      frameBuilder:
                          (ctx, child, frame, wasSynchronouslyLoaded) {
                        if (wasSynchronouslyLoaded) return child;
                        return AnimatedOpacity(
                          opacity: frame == null ? 0.0 : 1.0,
                          duration: const Duration(milliseconds: 300),
                          child: frame == null
                              ? _GradientBackground(
                                  colors: gradient, icon: icon)
                              : child,
                        );
                      },
                      errorBuilder: (_, _, _) =>
                          _GradientBackground(colors: gradient, icon: icon),
                    )
                  else
                    _GradientBackground(colors: gradient, icon: icon),

                  // ── Bottom dark gradient overlay ──────────────────
                  Positioned.fill(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          stops: const [0.30, 1.0],
                          colors: [
                            Colors.transparent,
                            Colors.black.withValues(alpha: 0.80),
                          ],
                        ),
                      ),
                    ),
                  ),

                  // ── File-available indicator (top-right) ──────────
                  if (hasFile)
                    Positioned(
                      top: 10,
                      right: 10,
                      child: Container(
                        padding: const EdgeInsets.all(5),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.45),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Icon(
                          Icons.download_rounded,
                          color: Colors.white,
                          size: 14,
                        ),
                      ),
                    ),

                  // ── Metadata overlay at bottom ────────────────────
                  Positioned(
                    left: 10,
                    right: 10,
                    bottom: 10,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        // Type badge
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 7, vertical: 2),
                              decoration: BoxDecoration(
                                color: accent,
                                borderRadius: BorderRadius.circular(5),
                              ),
                              child: Text(
                                typeLabel,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 9,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: 0.6,
                                ),
                              ),
                            ),
                            if (resource.publicationDate != null) ...[
                              const SizedBox(width: 6),
                              Text(
                                _formatDate(resource.publicationDate!),
                                style: TextStyle(
                                  color: Colors.white.withValues(alpha: 0.70),
                                  fontSize: 10,
                                ),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 5),
                        // Title
                        Text(
                          title,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w700,
                            height: 1.25,
                            shadows: [
                              Shadow(
                                color: Colors.black54,
                                blurRadius: 4,
                              ),
                            ],
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ── Gradient background (no thumbnail) ────────────────────────────────────

class _GradientBackground extends StatelessWidget {
  final List<Color> colors;
  final IconData icon;

  const _GradientBackground({required this.colors, required this.icon});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: colors,
        ),
      ),
      child: Center(
        child: Icon(
          icon,
          size: 64,
          color: Colors.white.withValues(alpha: 0.18),
        ),
      ),
    );
  }
}

// ── Shimmer skeleton ───────────────────────────────────────────────────────

class _ShimmerGrid extends StatelessWidget {
  const _ShimmerGrid();

  @override
  Widget build(BuildContext context) {
    return GridView.builder(
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 24),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 2,
        crossAxisSpacing: 12,
        mainAxisSpacing: 12,
        childAspectRatio: 0.66,
      ),
      itemCount: 6,
      itemBuilder: (_, _) => const _ShimmerCard(),
    );
  }
}

class _ShimmerCard extends StatefulWidget {
  const _ShimmerCard();

  @override
  State<_ShimmerCard> createState() => _ShimmerCardState();
}

class _ShimmerCardState extends State<_ShimmerCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1100),
    )..repeat(reverse: true);
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final base = isDark ? const Color(0xFF2C2C2E) : const Color(0xFFE5E5EA);
    final highlight =
        isDark ? const Color(0xFF3A3A3C) : const Color(0xFFF2F2F7);

    return AnimatedBuilder(
      animation: _anim,
      builder: (_, _) => ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                Color.lerp(base, highlight, _anim.value)!,
                Color.lerp(highlight, base, _anim.value)!,
              ],
            ),
          ),
          child: Stack(
            children: [
              // Bottom placeholder lines
              Positioned(
                left: 10,
                right: 10,
                bottom: 10,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 56,
                      height: 12,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Container(
                      width: double.infinity,
                      height: 10,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                    const SizedBox(height: 4),
                    Container(
                      width: 80,
                      height: 10,
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.10),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
