import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../config/routes.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/unified_planning_document.dart';
import '../../providers/public/public_resources_provider.dart';
import '../../services/unified_planning_pdf_thumbnail_cache.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';

/// Client-side list ordering for [UnifiedPlanningDocumentsScreen].
enum UnifiedPlanningListSort {
  /// [UnifiedPlanningDocument.publishedAt] descending; missing dates last.
  dateNewestFirst,

  /// [UnifiedPlanningDocument.publishedAt] ascending; missing dates last.
  dateOldestFirst,

  /// [UnifiedPlanningDocument.countryName] A→Z, then title.
  countryNameAz,

  /// [UnifiedPlanningDocument.countryName] Z→A, then title.
  countryNameZa,
}

/// IFRC GO unified planning PDFs (PublicSiteAppeals) — opened from [ResourcesScreen].
///
/// The IFRC list API returns the full set in one response; we paginate in the UI
/// (first [ _pageSize ] items, then load more). Filters apply client-side.
class UnifiedPlanningDocumentsScreen extends StatefulWidget {
  const UnifiedPlanningDocumentsScreen({super.key});

  @override
  State<UnifiedPlanningDocumentsScreen> createState() =>
      _UnifiedPlanningDocumentsScreenState();
}

class _UnifiedPlanningDocumentsScreenState
    extends State<UnifiedPlanningDocumentsScreen> {
  final TextEditingController _searchController = TextEditingController();

  /// Client-side page size (IFRC fetch is single-shot).
  static const int _pageSize = 20;

  int _visibleCount = _pageSize;

  /// Country display name; null = all.
  String? _filterCountryName;

  /// [UnifiedPlanningDocument.appealsTypeId]; null = all.
  int? _filterTypeId;

  /// Document year; null = all.
  int? _filterYear;

  /// Sort order (applied after search + attribute filters).
  UnifiedPlanningListSort _sortMode = UnifiedPlanningListSort.dateNewestFirst;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<PublicResourcesProvider>().loadUnifiedPlanningDocuments();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _resetPagination() {
    setState(() => _visibleCount = _pageSize);
  }

  /// `true` when opened via [Navigator.pushNamed] (e.g. from Resources); `false`
  /// when embedded as a main [PageView] tab.
  bool _isStandaloneScreen(BuildContext context) {
    final route = ModalRoute.of(context);
    final routeName = route?.settings.name;
    if (routeName == AppRoutes.unifiedPlanningDocuments) return true;
    if (routeName == null || routeName == AppRoutes.dashboard) return false;
    return Navigator.of(context).canPop();
  }

  List<UnifiedPlanningDocument> _searchFiltered(
    List<UnifiedPlanningDocument> all,
    String q,
  ) {
    final t = q.trim().toLowerCase();
    if (t.isEmpty) return all;
    return all
        .where((d) {
          final hay =
              '${d.title} ${d.countryName ?? ''} ${d.documentTypeLabel ?? ''} ${d.countryCode ?? ''}'
                  .toLowerCase();
          return hay.contains(t);
        })
        .toList(growable: false);
  }

  List<UnifiedPlanningDocument> _attributeFiltered(
    List<UnifiedPlanningDocument> all,
  ) {
    return all.where((d) {
      if (_filterCountryName != null) {
        final n = (d.countryName ?? '').trim().toLowerCase();
        if (n != _filterCountryName!.trim().toLowerCase()) return false;
      }
      if (_filterTypeId != null && d.appealsTypeId != _filterTypeId) {
        return false;
      }
      if (_filterYear != null && d.year != _filterYear) return false;
      return true;
    }).toList(growable: false);
  }

  static int _titleCompare(UnifiedPlanningDocument a, UnifiedPlanningDocument b) {
    return a.title.toLowerCase().compareTo(b.title.toLowerCase());
  }

  /// Stable ordering after attribute filter + search; does not mutate [list].
  List<UnifiedPlanningDocument> _sortedCopy(
    List<UnifiedPlanningDocument> list,
    UnifiedPlanningListSort mode,
  ) {
    int comparePublishedAscending(UnifiedPlanningDocument a, UnifiedPlanningDocument b) {
      final da = a.publishedAt;
      final db = b.publishedAt;
      if (da == null && db == null) return _titleCompare(a, b);
      if (da == null) return 1;
      if (db == null) return -1;
      final c = da.compareTo(db);
      if (c != 0) return c;
      return _titleCompare(a, b);
    }

    int compareCountryThenTitle(UnifiedPlanningDocument a, UnifiedPlanningDocument b) {
      final ca = (a.countryName ?? '').trim().toLowerCase();
      final cb = (b.countryName ?? '').trim().toLowerCase();
      if (ca.isEmpty && cb.isEmpty) return _titleCompare(a, b);
      if (ca.isEmpty) return 1;
      if (cb.isEmpty) return -1;
      final c = ca.compareTo(cb);
      if (c != 0) return c;
      return _titleCompare(a, b);
    }

    int compareCountryThenTitleReverse(UnifiedPlanningDocument a, UnifiedPlanningDocument b) {
      final ca = (a.countryName ?? '').trim().toLowerCase();
      final cb = (b.countryName ?? '').trim().toLowerCase();
      if (ca.isEmpty && cb.isEmpty) return _titleCompare(a, b);
      if (ca.isEmpty) return 1;
      if (cb.isEmpty) return -1;
      final c = cb.compareTo(ca);
      if (c != 0) return c;
      return _titleCompare(a, b);
    }

    final out = list.toList();
    switch (mode) {
      case UnifiedPlanningListSort.dateNewestFirst:
        out.sort((a, b) {
          final da = a.publishedAt;
          final db = b.publishedAt;
          if (da == null && db == null) return _titleCompare(a, b);
          if (da == null) return 1;
          if (db == null) return -1;
          final c = -da.compareTo(db);
          if (c != 0) return c;
          return _titleCompare(a, b);
        });
        break;
      case UnifiedPlanningListSort.dateOldestFirst:
        out.sort(comparePublishedAscending);
        break;
      case UnifiedPlanningListSort.countryNameAz:
        out.sort(compareCountryThenTitle);
        break;
      case UnifiedPlanningListSort.countryNameZa:
        out.sort(compareCountryThenTitleReverse);
        break;
    }
    return out;
  }

  String _sortModeLabel(AppLocalizations loc, UnifiedPlanningListSort mode) {
    switch (mode) {
      case UnifiedPlanningListSort.dateNewestFirst:
        return loc.unifiedPlanningSortDateNewest;
      case UnifiedPlanningListSort.dateOldestFirst:
        return loc.unifiedPlanningSortDateOldest;
      case UnifiedPlanningListSort.countryNameAz:
        return loc.unifiedPlanningSortCountryAz;
      case UnifiedPlanningListSort.countryNameZa:
        return loc.unifiedPlanningSortCountryZa;
    }
  }

  List<String> _distinctCountryNames(List<UnifiedPlanningDocument> all) {
    final set = <String>{};
    for (final d in all) {
      final n = d.countryName?.trim();
      if (n != null && n.isNotEmpty) set.add(n);
    }
    final out = set.toList()..sort((a, b) => a.toLowerCase().compareTo(b.toLowerCase()));
    return out;
  }

  List<MapEntry<int, String>> _distinctTypes(List<UnifiedPlanningDocument> all) {
    final map = <int, String>{};
    for (final d in all) {
      final id = d.appealsTypeId;
      if (id == null) continue;
      final label = (d.documentTypeLabel ?? '').trim();
      map[id] = label.isNotEmpty ? label : 'Type $id';
    }
    final entries = map.entries.toList()
      ..sort((a, b) => a.value.toLowerCase().compareTo(b.value.toLowerCase()));
    return entries;
  }

  List<int> _distinctYears(List<UnifiedPlanningDocument> all) {
    final set = <int>{};
    for (final d in all) {
      final y = d.year;
      if (y != null) set.add(y);
    }
    final out = set.toList()..sort((a, b) => b.compareTo(a));
    return out;
  }

  String? _errorMessage(AppLocalizations loc, String? code) {
    switch (code) {
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

  void _openPdf(BuildContext context, String url, String title) {
    Navigator.of(context).pushNamed(
      AppRoutes.pdfViewer,
      arguments: <String, String>{
        'url': url,
        'title': title,
        'thumbnailCacheUrl': url,
      },
    );
  }

  bool get _hasActiveFilters =>
      _filterCountryName != null ||
      _filterTypeId != null ||
      _filterYear != null ||
      _sortMode != UnifiedPlanningListSort.dateNewestFirst;

  Future<void> _openFiltersSheet(
    BuildContext context,
    AppLocalizations loc,
    List<UnifiedPlanningDocument> all,
  ) async {
    final countries = _distinctCountryNames(all);
    final types = _distinctTypes(all);
    final years = _distinctYears(all);

    String? tempCountry = _filterCountryName;
    int? tempType = _filterTypeId;
    int? tempYear = _filterYear;
    var tempSort = _sortMode;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 8,
            bottom: MediaQuery.of(ctx).padding.bottom + 16,
          ),
          child: StatefulBuilder(
            builder: (context, setModalState) {
              final menuMaxH = _filterSheetMenuMaxHeight(context);
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    loc.indicatorBankFilters,
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w800,
                        ),
                  ),
                  const SizedBox(height: 12),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      loc.unifiedPlanningSortBy,
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<UnifiedPlanningListSort>(
                    key: ValueKey<UnifiedPlanningListSort>(tempSort),
                    initialValue: tempSort,
                    isExpanded: true,
                    menuMaxHeight: menuMaxH,
                    decoration: _filterFieldDecoration(context),
                    items: [
                      for (final m in UnifiedPlanningListSort.values)
                        DropdownMenuItem<UnifiedPlanningListSort>(
                          value: m,
                          child: Text(
                            _sortModeLabel(loc, m),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                    ],
                    onChanged: (v) {
                      if (v == null) return;
                      setModalState(() => tempSort = v);
                    },
                  ),
                  const SizedBox(height: 14),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      loc.countries,
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<String?>(
                    key: ValueKey<String?>(tempCountry),
                    initialValue: tempCountry,
                    isExpanded: true,
                    menuMaxHeight: menuMaxH,
                    decoration: _filterFieldDecoration(context),
                    items: [
                      DropdownMenuItem<String?>(
                        value: null,
                        child: Text(loc.unifiedPlanningFilterAllCountries),
                      ),
                      ...countries.map(
                        (c) => DropdownMenuItem<String?>(
                          value: c,
                          child: Text(c, overflow: TextOverflow.ellipsis),
                        ),
                      ),
                    ],
                    onChanged: (v) => setModalState(() => tempCountry = v),
                  ),
                  const SizedBox(height: 14),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      loc.indicatorBankFilterType,
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<int?>(
                    key: ValueKey<String>('unified_filter_type_$tempType'),
                    initialValue: tempType,
                    isExpanded: true,
                    menuMaxHeight: menuMaxH,
                    decoration: _filterFieldDecoration(context),
                    items: [
                      DropdownMenuItem<int?>(
                        value: null,
                        child: Text(loc.indicatorBankFilterTypeAll),
                      ),
                      ...types.map(
                        (e) => DropdownMenuItem<int?>(
                          value: e.key,
                          child: Text(e.value, overflow: TextOverflow.ellipsis),
                        ),
                      ),
                    ],
                    onChanged: (v) => setModalState(() => tempType = v),
                  ),
                  const SizedBox(height: 14),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      'Year',
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                  const SizedBox(height: 6),
                  DropdownButtonFormField<int?>(
                    key: ValueKey<String>('unified_filter_year_$tempYear'),
                    initialValue: tempYear,
                    isExpanded: true,
                    menuMaxHeight: menuMaxH,
                    decoration: _filterFieldDecoration(context),
                    items: [
                      DropdownMenuItem<int?>(
                        value: null,
                        child: Text(loc.allYears),
                      ),
                      ...years.map(
                        (y) => DropdownMenuItem<int?>(
                          value: y,
                          child: Text('$y'),
                        ),
                      ),
                    ],
                    onChanged: (v) => setModalState(() => tempYear = v),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () {
                            setState(() {
                              _filterCountryName = null;
                              _filterTypeId = null;
                              _filterYear = null;
                              _sortMode = UnifiedPlanningListSort.dateNewestFirst;
                              _resetPagination();
                            });
                            Navigator.pop(ctx);
                          },
                          child: Text(loc.adminFiltersClear),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(
                          style: FilledButton.styleFrom(
                            backgroundColor: Color(AppConstants.ifrcRed),
                          ),
                          onPressed: () {
                            setState(() {
                              _filterCountryName = tempCountry;
                              _filterTypeId = tempType;
                              _filterYear = tempYear;
                              _sortMode = tempSort;
                              _resetPagination();
                            });
                            Navigator.pop(ctx);
                          },
                          child: Text(loc.adminFiltersApply),
                        ),
                      ),
                    ],
                  ),
                ],
              );
            },
          ),
        );
      },
    );
  }

  static InputDecoration _filterFieldDecoration(BuildContext context) {
    return InputDecoration(
      filled: true,
      fillColor: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.4),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: BorderSide.none,
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
    );
  }

  /// Keeps [DropdownButton] menus from using the full screen height; reads as in-sheet.
  static double _filterSheetMenuMaxHeight(BuildContext context) {
    final h = MediaQuery.sizeOf(context).height;
    return (h * 0.36).clamp(200.0, 300.0);
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final standalone = _isStandaloneScreen(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.resourcesUnifiedPlanningSectionTitle,
        leading: standalone
            ? IconButton(
                icon: const Icon(Icons.arrow_back_rounded),
                onPressed: () => Navigator.of(context).pop(),
                tooltip: MaterialLocalizations.of(context).backButtonTooltip,
              )
            : null,
        automaticallyImplyLeading: standalone,
        actions: [
          IconButton(
            icon: const Icon(Icons.insights_rounded),
            tooltip: loc.unifiedPlanningAnalyticsTooltip,
            onPressed: () => Navigator.of(context).pushNamed(
              AppRoutes.unifiedPlanningAnalytics,
            ),
          ),
          Consumer<PublicResourcesProvider>(
            builder: (context, provider, _) {
              final all = provider.unifiedPlanningDocuments;
              return IconButton(
                icon: Badge(
                  isLabelVisible: _hasActiveFilters,
                  smallSize: 8,
                  child: const Icon(Icons.tune_rounded),
                ),
                tooltip: loc.indicatorBankFilters,
                onPressed: all.isEmpty && provider.unifiedPlanningLoading
                    ? null
                    : () => _openFiltersSheet(context, loc, all),
              );
            },
          ),
        ],
      ),
      body: Consumer<PublicResourcesProvider>(
        builder: (context, provider, _) {
          final all = provider.unifiedPlanningDocuments;
          final searched = _searchFiltered(all, _searchController.text);
          final filtered =
              _sortedCopy(_attributeFiltered(searched), _sortMode);
          final visible = filtered.take(_visibleCount).toList(growable: false);
          final hasMore = _visibleCount < filtered.length;
          final err = _errorMessage(loc, provider.unifiedPlanningErrorCode);

          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 8, 14, 8),
                child: TextField(
                  controller: _searchController,
                  onChanged: (_) {
                    _resetPagination();
                    setState(() {});
                  },
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    hintText: loc.searchResources,
                    hintStyle:
                        TextStyle(color: context.textSecondaryColor),
                    prefixIcon:
                        Icon(Icons.search_rounded, color: context.iconColor),
                    suffixIcon: _searchController.text.isNotEmpty
                        ? IconButton(
                            icon: Icon(Icons.clear_rounded,
                                color: context.iconColor),
                            onPressed: () {
                              _searchController.clear();
                              _resetPagination();
                              setState(() {});
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
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                    isDense: true,
                  ),
                ),
              ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () async {
                    _resetPagination();
                    await context
                        .read<PublicResourcesProvider>()
                        .loadUnifiedPlanningDocuments();
                  },
                  color: Color(AppConstants.ifrcRed),
                  child: _buildScrollableBody(
                    context,
                    loc,
                    theme,
                    provider,
                    filtered,
                    visible,
                    hasMore,
                    err,
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildScrollableBody(
    BuildContext context,
    AppLocalizations loc,
    ThemeData theme,
    PublicResourcesProvider provider,
    List<UnifiedPlanningDocument> filtered,
    List<UnifiedPlanningDocument> visible,
    bool hasMore,
    String? err,
  ) {
    final bottomPad =
        MediaQuery.viewPaddingOf(context).bottom + 24;

    if (provider.unifiedPlanningLoading && provider.unifiedPlanningDocuments.isEmpty) {
      return CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          SliverPadding(
            padding: EdgeInsets.fromLTRB(14, 10, 14, bottomPad),
            sliver: SliverGrid(
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
                childAspectRatio: 0.66,
              ),
              delegate: SliverChildBuilderDelegate(
                (context, index) => const _UnifiedPlanningShimmerCard(),
                childCount: 6,
              ),
            ),
          ),
        ],
      );
    }

    if (err != null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + bottomPad),
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color:
                  const Color(AppConstants.errorColor).withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: const Color(AppConstants.errorColor)
                    .withValues(alpha: 0.25),
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
          ),
        ],
      );
    }

    if (filtered.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + bottomPad),
        children: [
          Text(
            loc.unifiedPlanningEmpty,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: context.textSecondaryColor,
            ),
          ),
        ],
      );
    }

    return CustomScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(14, 4, 14, 8),
          sliver: SliverGrid(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 2,
              crossAxisSpacing: 12,
              mainAxisSpacing: 12,
              childAspectRatio: 0.66,
            ),
            delegate: SliverChildBuilderDelegate(
              (context, index) {
                final d = visible[index];
                return _UnifiedPlanningDocCard(
                  key: ValueKey(d.url),
                  document: d,
                  index: index,
                  onOpen: () => _openPdf(context, d.url, d.title),
                );
              },
              childCount: visible.length,
            ),
          ),
        ),
        if (hasMore)
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.fromLTRB(14, 0, 14, 16 + bottomPad),
              child: Center(
                child: TextButton.icon(
                  onPressed: () {
                    setState(() {
                      _visibleCount += _pageSize;
                    });
                  },
                  icon: const Icon(Icons.expand_more_rounded),
                  label: Text(loc.sessionLogsLoadMore),
                  style: TextButton.styleFrom(
                    foregroundColor: Color(AppConstants.ifrcRed),
                  ),
                ),
              ),
            ),
          )
        else
          SliverToBoxAdapter(child: SizedBox(height: 16 + bottomPad)),
      ],
    );
  }
}

// ── Grid card (matches resources [ _ResourceCard ] layout — gradient + overlay) ─

class _UnifiedPlanningDocCard extends StatefulWidget {
  final UnifiedPlanningDocument document;
  final int index;
  final VoidCallback onOpen;

  const _UnifiedPlanningDocCard({
    super.key,
    required this.document,
    required this.index,
    required this.onOpen,
  });

  @override
  State<_UnifiedPlanningDocCard> createState() => _UnifiedPlanningDocCardState();
}

class _UnifiedPlanningDocCardState extends State<_UnifiedPlanningDocCard>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pressController;
  late final Animation<double> _scale;
  Uint8List? _thumbJpeg;
  StreamSubscription<String>? _thumbReadySub;

  static List<Color> _gradientForDoc(UnifiedPlanningDocument d) {
    final label = (d.documentTypeLabel ?? '').toLowerCase();
    if (label.contains('mid')) {
      return [const Color(0xFFE65100), const Color(0xFFFF6D00)];
    }
    if (label.contains('annual')) {
      return [const Color(0xFF1B5E20), const Color(0xFF388E3C)];
    }
    if (label.contains('plan')) {
      return [const Color(0xFF0D47A1), const Color(0xFF1976D2)];
    }
    return [const Color(0xFF4A148C), const Color(0xFF7B1FA2)];
  }

  static Color _accentForDoc(UnifiedPlanningDocument d) {
    final g = _gradientForDoc(d);
    return g.first;
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

    final cache = UnifiedPlanningPdfThumbnailCache.instance;
    _thumbJpeg = cache.readThumbnailSync(widget.document.url);
    cache.getThumbnail(widget.document.url).then((bytes) {
      if (!mounted) return;
      if (bytes == _thumbJpeg) return;
      setState(() => _thumbJpeg = bytes);
    });
    final docUrl = widget.document.url.trim();
    _thumbReadySub = cache.thumbnailReady.listen((u) {
      if (u.trim() != docUrl) return;
      if (!mounted) return;
      final b = cache.readThumbnailSync(widget.document.url);
      if (b != null && b.isNotEmpty) {
        setState(() => _thumbJpeg = b);
      }
    });
  }

  @override
  void dispose() {
    _thumbReadySub?.cancel();
    _pressController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final d = widget.document;
    final gradient = _gradientForDoc(d);
    final accent = _accentForDoc(d);
    final typeLabel = (d.documentTypeLabel?.trim().isNotEmpty ?? false)
        ? d.documentTypeLabel!.trim()
        : loc.document;
    final title = d.title.trim().isNotEmpty ? d.title.trim() : loc.document;

    return GestureDetector(
      onTapDown: (_) => _pressController.forward(),
      onTapUp: (_) {
        _pressController.reverse();
        widget.onOpen();
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
              _GradientBackground(
                colors: gradient,
                icon: Icons.picture_as_pdf_rounded,
              ),
              if (_thumbJpeg != null && _thumbJpeg!.isNotEmpty)
                Positioned.fill(
                  child: Image.memory(
                    _thumbJpeg!,
                    fit: BoxFit.cover,
                    gaplessPlayback: true,
                    errorBuilder: (context, error, stackTrace) =>
                        const SizedBox.shrink(),
                  ),
                ),
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
              if (d.isPublishedWithinLastThreeDays)
                Positioned.fill(
                  child: _FreshCenterStripe(
                    label: loc.unifiedPlanningFreshBadge,
                  ),
                ),
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
              Positioned(
                left: 10,
                right: 10,
                bottom: 10,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        // Use [Flexible] with loose fit so the chip hugs the label; [Expanded]
                        // would stretch the badge across the full row minus the year.
                        Flexible(
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 7, vertical: 2),
                            decoration: BoxDecoration(
                              color: accent,
                              borderRadius: BorderRadius.circular(5),
                            ),
                            child: Text(
                              typeLabel,
                              maxLines: 1,
                              softWrap: false,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 9,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 0.6,
                              ),
                            ),
                          ),
                        ),
                        if (d.year != null) ...[
                          const SizedBox(width: 6),
                          Text(
                            '${d.year}',
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.70),
                              fontSize: 10,
                            ),
                          ),
                        ],
                      ],
                    ),
                    if ((d.countryName ?? '').trim().isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        d.countryName!.trim(),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          color: Colors.white.withValues(alpha: 0.85),
                          fontSize: 10,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                    const SizedBox(height: 5),
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
    );
  }
}

/// Full-width red band, centered; “Fresh” text scrolls in a news-ticker loop.
class _FreshCenterStripe extends StatefulWidget {
  final String label;

  const _FreshCenterStripe({required this.label});

  @override
  State<_FreshCenterStripe> createState() => _FreshCenterStripeState();
}

class _FreshCenterStripeState extends State<_FreshCenterStripe>
    with SingleTickerProviderStateMixin {
  late final AnimationController _marquee;
  static const double _kStripeHeight = 22;
  static const double _scrollPxPerSec = 38;

  /// Width of one repeating cell (`  label  ·  `).
  double _unitW = 0;

  @override
  void initState() {
    super.initState();
    _marquee = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 5000),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => _measureTickerUnit());
  }

  @override
  void didUpdateWidget(covariant _FreshCenterStripe oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.label != widget.label) {
      _marquee
        ..stop()
        ..reset();
      setState(() => _unitW = 0);
      WidgetsBinding.instance.addPostFrameCallback((_) => _measureTickerUnit());
    }
  }

  @override
  void dispose() {
    _marquee.dispose();
    super.dispose();
  }

  String _tickerCell() => '  ${widget.label}  ·  ';

  void _measureTickerUnit() {
    if (!mounted) return;
    final style = const TextStyle(
      color: Colors.white,
      fontSize: 11,
      fontWeight: FontWeight.w700,
      height: 1,
    );
    final tp = TextPainter(
      text: TextSpan(text: _tickerCell(), style: style),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    final w = tp.width;
    if (w <= 0) return;
    if ((w - _unitW).abs() < 0.5) {
      if (_unitW > 0 && !_marquee.isAnimating) {
        _marquee.repeat();
      }
      return;
    }
    final ms = (w / _scrollPxPerSec * 1000).round().clamp(4000, 20000);
    setState(() {
      _unitW = w;
      _marquee
        ..duration = Duration(milliseconds: ms)
        ..reset()
        ..repeat();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_unitW <= 0) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _measureTickerUnit());
    }
  }

  @override
  Widget build(BuildContext context) {
    final red = Color(AppConstants.ifrcRed);
    const style = TextStyle(
      color: Colors.white,
      fontSize: 11,
      fontWeight: FontWeight.w700,
      height: 1,
    );

    if (_unitW <= 0) {
      return IgnorePointer(
        child: Center(
          child: SizedBox(
            height: _kStripeHeight,
            width: double.infinity,
            child: ColoredBox(
              color: red,
              child: Center(
                child: Text(
                  widget.label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: style,
                ),
              ),
            ),
          ),
        ),
      );
    }

    return IgnorePointer(
      child: Center(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final w = constraints.maxWidth;
            final copies = w <= 0
                ? 4
                : (w / _unitW).ceil() + 2;
            return SizedBox(
              height: _kStripeHeight,
              width: double.infinity,
              child: ClipRect(
                child: ColoredBox(
                  color: red,
                  // Row is intentionally wider than the viewport (marquee). Give it
                  // unbounded width so it does not trigger RenderFlex overflow; we clip
                  // above. (copies * measured unit width can still exceed [w] when
                  // text scale factor differs from TextPainter.)
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: UnconstrainedBox(
                      constrainedAxis: Axis.vertical,
                      clipBehavior: Clip.hardEdge,
                      alignment: Alignment.centerLeft,
                      child: SizedBox(
                        height: _kStripeHeight,
                        child: AnimatedBuilder(
                          animation: _marquee,
                          builder: (context, child) {
                            return Transform.translate(
                              offset: Offset(-_unitW * _marquee.value, 0),
                              child: child,
                            );
                          },
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: List<Widget>.generate(
                              copies.clamp(3, 24),
                              (_) => Text(
                                _tickerCell(),
                                maxLines: 1,
                                style: style,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

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

class _UnifiedPlanningShimmerCard extends StatefulWidget {
  const _UnifiedPlanningShimmerCard();

  @override
  State<_UnifiedPlanningShimmerCard> createState() =>
      _UnifiedPlanningShimmerCardState();
}

class _UnifiedPlanningShimmerCardState extends State<_UnifiedPlanningShimmerCard>
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
        ),
      ),
    );
  }
}
