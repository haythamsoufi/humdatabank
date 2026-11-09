import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/shared/language_provider.dart';
import '../../services/api_service.dart';
import '../../services/offline_cache_service.dart';
import '../../services/public_browse_prefetch.dart';
import '../../utils/constants.dart';
import '../../utils/network_availability.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/empty_state.dart';
import '../../widgets/error_state.dart';

class CountriesScreen extends StatefulWidget {
  const CountriesScreen({super.key});

  @override
  State<CountriesScreen> createState() => _CountriesScreenState();
}

class _CountriesScreenState extends State<CountriesScreen> {
  static const double _wideLayoutBreakpoint = 768;

  /// Seeded sandbox countries. They exist for backoffice testing and are not
  /// real National Societies, so they stay off the public list.
  static const Set<String> _hiddenCountryNames = {'testland', 'testlantica'};
  static const Set<String> _hiddenCountryIso3 = {'TST'};

  final ApiService _apiService = sl<ApiService>();
  final ScrollController _scrollController = ScrollController();
  final TextEditingController _searchController = TextEditingController();
  List<Map<String, dynamic>> _countries = [];
  bool _isLoading = true;
  bool _hasError = false;
  String _searchQuery = '';
  String? _selectedRegion;
  Map<String, List<Map<String, dynamic>>> _countriesByRegion = {};

  bool get _isSearching => _searchQuery.trim().isNotEmpty;

  @override
  void initState() {
    super.initState();
    _loadCountries();
  }

  @override
  void dispose() {
    _scrollController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  static bool _isHiddenCountry(Map<String, dynamic> country) {
    final iso3 = (country['iso3'] as String?)?.trim().toUpperCase();
    if (iso3 != null && _hiddenCountryIso3.contains(iso3)) return true;
    for (final key in ['name', 'localized_name']) {
      final value = (country[key] as String?)?.trim().toLowerCase();
      if (value != null && _hiddenCountryNames.contains(value)) return true;
    }
    return false;
  }

  static String _displayName(Map<String, dynamic> country) {
    final localized = (country['localized_name'] as String?)?.trim();
    if (localized != null && localized.isNotEmpty) return localized;
    final name = (country['name'] as String?)?.trim();
    return (name != null && name.isNotEmpty) ? name : 'Unknown';
  }

  Future<void> _loadCountries({bool refresh = false}) async {
    if (!refresh) {
      setState(() {
        _isLoading = true;
        _hasError = false;
      });
    }

    try {
      final languageProvider =
          Provider.of<LanguageProvider>(context, listen: false);
      final language = languageProvider.currentLanguage;
      sl<PublicBrowsePrefetch>().warm(locale: language, force: refresh);

      // ApiService stores this response and serves it when the device is
      // offline or the backend cannot be reached.
      final response = await _apiService.get(
        AppConfig.mobileCountryMapEndpoint,
        queryParams: {
          'locale': language,
        },
        includeAuth: false,
        cacheTtl: OfflineCacheService.publicBrowseTtl,
      );

      if (!mounted) return;
      if (response.statusCode != 200) {
        _handleLoadFailure();
        return;
      }

      final decoded = jsonDecode(response.body);
      final List<dynamic> data;
      if (decoded is List) {
        data = decoded;
      } else if (decoded is Map<String, dynamic> && decoded['data'] is Map) {
        data = (decoded['data'] as Map)['countries'] as List<dynamic>? ?? [];
      } else if (decoded is Map<String, dynamic> && decoded['data'] is List) {
        data = decoded['data'] as List<dynamic>;
      } else {
        data = [];
      }
      final List<Map<String, dynamic>> countries = data
          .map((item) => item as Map<String, dynamic>)
          .where((country) => !_isHiddenCountry(country))
          .toList();

      final Map<String, List<Map<String, dynamic>>> grouped = {};
      for (final country in countries) {
        final region = country['region_localized'] as String? ??
            country['region'] as String? ??
            'Other';
        grouped.putIfAbsent(region, () => []).add(country);
      }

      final sortedRegions = grouped.keys.toList()..sort();
      final sortedGrouped =
          Map<String, List<Map<String, dynamic>>>.fromEntries(
        sortedRegions.map((region) => MapEntry(region, grouped[region]!)),
      );

      for (final list in sortedGrouped.values) {
        list.sort(
          (a, b) => _displayName(a)
              .toLowerCase()
              .compareTo(_displayName(b).toLowerCase()),
        );
      }

      setState(() {
        _countries = countries;
        _countriesByRegion = sortedGrouped;
        if (_selectedRegion == null ||
            !sortedGrouped.containsKey(_selectedRegion)) {
          _selectedRegion =
              sortedRegions.isNotEmpty ? sortedRegions.first : null;
        }
        _hasError = false;
        _isLoading = false;
      });
    } catch (e) {
      if (!mounted) return;
      _handleLoadFailure();
    }
  }

  void _handleLoadFailure() {
    setState(() {
      _hasError = _countries.isEmpty;
      _isLoading = false;
    });
  }

  List<Map<String, dynamic>> _getFilteredCountries() {
    if (!_isSearching) {
      if (_selectedRegion == null) return [];
      return _countriesByRegion[_selectedRegion] ?? [];
    }

    final query = _searchQuery.trim().toLowerCase();
    return _countries.where((country) {
      final haystack = [
        country['name'],
        country['localized_name'],
        country['national_society_name'],
        country['localized_national_society_name'],
        country['iso3'],
        country['iso2'],
      ].whereType<String>().map((s) => s.toLowerCase());
      return haystack.any((value) => value.contains(query));
    }).toList()
      ..sort(
        (a, b) => _displayName(a)
            .toLowerCase()
            .compareTo(_displayName(b).toLowerCase()),
      );
  }

  void _navigateToCountry(String iso3, String name) {
    Navigator.of(context).pushNamed(
      AppRoutes.countryDetail(iso3),
      arguments: name,
    );
  }

  void _selectRegion(String region) {
    _searchController.clear();
    setState(() {
      _selectedRegion = region;
      _searchQuery = '';
    });
    if (_scrollController.hasClients) {
      _scrollController.jumpTo(0);
    }
  }

  void _clearSearch() {
    _searchController.clear();
    setState(() => _searchQuery = '');
  }

  /// `true` when opened via [Navigator.pushNamed]; `false` inside the tab shell.
  bool _isStandaloneScreen(BuildContext context) {
    final routeName = ModalRoute.of(context)?.settings.name;
    if (routeName == AppRoutes.countries) return true;
    if (routeName == null || routeName == AppRoutes.dashboard) return false;
    return Navigator.of(context).canPop();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(title: localizations.countries),
      bottomNavigationBar: _isStandaloneScreen(context)
          ? AppBottomNavigationBar.shellTabBar
          : null,
      body: _buildBody(context, localizations),
    );
  }

  Widget _buildBody(BuildContext context, AppLocalizations localizations) {
    if (_isLoading) {
      return Semantics(
        label: localizations.countriesLoading,
        child: const _CountriesGridShimmer(),
      );
    }

    if (_hasError) {
      return AppErrorState(
        message: shouldDeferRemoteFetch
            ? localizations.offlineNoInternet
            : localizations.oopsSomethingWentWrong,
        showTitle: false,
        onRetry: _loadCountries,
        retryStyle: AppErrorRetryStyle.materialFilled,
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final isWide = constraints.maxWidth >= _wideLayoutBreakpoint;

        if (!isWide) {
          return Column(
            children: [
              _buildSearchField(context, localizations),
              _buildRegionChips(context),
              Expanded(child: _buildCountriesList(context, localizations)),
            ],
          );
        }

        final sidebarWidth = (constraints.maxWidth * 0.25).clamp(220.0, 320.0);
        return Row(
          children: [
            SizedBox(
              width: sidebarWidth,
              child: _buildRegionSidebar(context, localizations),
            ),
            Expanded(
              child: Column(
                children: [
                  _buildSearchField(context, localizations),
                  Expanded(
                    child: _buildCountriesList(context, localizations),
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildSearchField(
    BuildContext context,
    AppLocalizations localizations,
  ) {
    final theme = Theme.of(context);
    final red = Color(AppConstants.ifrcRed);
    final radius = BorderRadius.circular(14);

    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 12),
      child: TextField(
        controller: _searchController,
        textInputAction: TextInputAction.search,
        onChanged: (value) => setState(() => _searchQuery = value),
        style: theme.textTheme.bodyLarge,
        decoration: InputDecoration(
          hintText: localizations.countriesSearchHint,
          hintStyle: theme.textTheme.bodyLarge?.copyWith(
            color: context.textSecondaryColor,
          ),
          prefixIcon: Icon(
            Icons.search_rounded,
            color: context.textSecondaryColor,
          ),
          suffixIcon: _searchQuery.isEmpty
              ? null
              : IconButton(
                  icon: const Icon(Icons.close_rounded, size: 20),
                  color: context.textSecondaryColor,
                  tooltip: MaterialLocalizations.of(context).clearButtonTooltip,
                  onPressed: _clearSearch,
                ),
          filled: true,
          fillColor: context.cardColor,
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          border: OutlineInputBorder(
            borderRadius: radius,
            borderSide: BorderSide(color: context.borderColor),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: radius,
            borderSide: BorderSide(color: context.borderColor),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: radius,
            borderSide: BorderSide(color: red, width: 1.5),
          ),
        ),
      ),
    );
  }

  Widget _buildRegionChips(BuildContext context) {
    final regions = _countriesByRegion.keys.toList();
    return SizedBox(
      height: 48,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: regions.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final region = regions[index];
          return Center(
            child: _RegionChip(
              label: region,
              count: _countriesByRegion[region]?.length ?? 0,
              selected: !_isSearching && _selectedRegion == region,
              onTap: () => _selectRegion(region),
            ),
          );
        },
      ),
    );
  }

  Widget _buildRegionSidebar(
    BuildContext context,
    AppLocalizations localizations,
  ) {
    final theme = Theme.of(context);
    final regions = _countriesByRegion.keys.toList();

    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border(
          right: BorderSide(color: context.dividerColor),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 16, 12),
            child: Text(
              localizations.countriesRegions,
              style: theme.textTheme.labelLarge?.copyWith(
                fontWeight: FontWeight.w700,
                letterSpacing: 0.4,
                color: context.textSecondaryColor,
              ),
            ),
          ),
          Expanded(
            child: ListView.separated(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 24),
              itemCount: regions.length,
              separatorBuilder: (_, _) => const SizedBox(height: 4),
              itemBuilder: (context, index) {
                final region = regions[index];
                final count = _countriesByRegion[region]?.length ?? 0;
                final selected = !_isSearching && _selectedRegion == region;
                return _RegionSidebarItem(
                  label: region,
                  subtitle: localizations.countriesCount(count),
                  selected: selected,
                  onTap: () => _selectRegion(region),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCountriesList(
    BuildContext context,
    AppLocalizations localizations,
  ) {
    final filtered = _getFilteredCountries();
    final textScaler = MediaQuery.textScalerOf(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final nameExtent = _countryNameExtent(textScaler);

    return RefreshIndicator(
      color: Color(AppConstants.ifrcRed),
      onRefresh: () => _loadCountries(refresh: true),
      child: CustomScrollView(
        controller: _scrollController,
        physics: const AlwaysScrollableScrollPhysics(),
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        slivers: [
          if (!_isSearching && _selectedRegion != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 6, 16, 12),
                child: _RegionOverviewBanner(
                  label: localizations.regionOverviewLink(_selectedRegion!),
                  onTap: () => Navigator.of(context).pushNamed(
                    AppRoutes.regionDetail(_selectedRegion!),
                    arguments: _selectedRegion,
                  ),
                ),
              ),
            ),
          if (filtered.isEmpty)
            SliverFillRemaining(
              hasScrollBody: false,
              child: Padding(
                padding: const EdgeInsets.only(bottom: 48),
                child: AppEmptyState(
                  icon: _isSearching
                      ? Icons.search_off_rounded
                      : Icons.public_off_rounded,
                  iconSize: 48,
                  title: _isSearching
                      ? localizations.countriesNoResults
                      : localizations.countriesNoAvailable,
                  subtitle: _isSearching ? '"${_searchQuery.trim()}"' : null,
                  action: _isSearching
                      ? TextButton(
                          onPressed: _clearSearch,
                          style: TextButton.styleFrom(
                            foregroundColor: context.linkOnSurfaceColor,
                          ),
                          child: Text(
                            MaterialLocalizations.of(context)
                                .clearButtonTooltip,
                          ),
                        )
                      : null,
                ),
              ),
            )
          else
            SliverPadding(
              padding: EdgeInsets.fromLTRB(16, 0, 16, bottomInset + 24),
              sliver: SliverGrid(
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  mainAxisExtent: nameExtent,
                  crossAxisSpacing: 0,
                  mainAxisSpacing: 0,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    final country = filtered[index];
                    final name = _displayName(country);
                    final rawIso3 = (country['iso3'] as String?)?.trim();
                    final iso3 = (rawIso3 != null && rawIso3.isNotEmpty)
                        ? rawIso3.toUpperCase()
                        : null;
                    return _CountryName(
                      name: name,
                      showEndDivider:
                          _countryGridShowsEndDivider(index, filtered.length),
                      showBottomDivider: _countryGridShowsBottomDivider(
                        index,
                        filtered.length,
                      ),
                      onTap: iso3 != null
                          ? () => _navigateToCountry(iso3, name)
                          : null,
                    );
                  },
                  childCount: filtered.length,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Two name lines plus vertical padding. Kept tall enough for a tap target.
double _countryNameExtent(TextScaler textScaler) {
  final name = textScaler.scale(15.5) * 1.3 * 2;
  return math.max(52, name + 28);
}

/// Vertical rule only between the two columns, and only when both cells exist.
bool _countryGridShowsEndDivider(int index, int count) =>
    index.isEven && index + 1 < count;

/// Horizontal rule between rows, not under the last row.
bool _countryGridShowsBottomDivider(int index, int count) {
  final lastRowStart = count - (count.isOdd ? 1 : 2);
  return index < lastRowStart;
}

BoxDecoration _countryGridLines({
  required Color color,
  required bool showEndDivider,
  required bool showBottomDivider,
}) {
  const hairline = 1.0;
  return BoxDecoration(
    border: BorderDirectional(
      end: showEndDivider
          ? BorderSide(color: color, width: hairline)
          : BorderSide.none,
      bottom: showBottomDivider
          ? BorderSide(color: color, width: hairline)
          : BorderSide.none,
    ),
  );
}

class _CountriesGridShimmer extends StatelessWidget {
  const _CountriesGridShimmer();

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final base = isDark
        ? const Color(AppConstants.semanticShimmerBaseDark)
        : const Color(AppConstants.semanticShimmerBaseLight);
    final highlight = isDark
        ? const Color(AppConstants.semanticShimmerHighlightDark)
        : const Color(AppConstants.semanticShimmerHighlightLight);
    final extent = _countryNameExtent(MediaQuery.textScalerOf(context));

    return Shimmer.fromColors(
      baseColor: base,
      highlightColor: highlight,
      period: const Duration(milliseconds: 1400),
      child: GridView.builder(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
        physics: const NeverScrollableScrollPhysics(),
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          mainAxisExtent: extent,
          crossAxisSpacing: 0,
          mainAxisSpacing: 0,
        ),
        itemCount: 12,
        itemBuilder: (context, index) => DecoratedBox(
          decoration: _countryGridLines(
            color: context.dividerColor,
            showEndDivider: _countryGridShowsEndDivider(index, 12),
            showBottomDivider: _countryGridShowsBottomDivider(index, 12),
          ),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: FractionallySizedBox(
              widthFactor: index.isEven ? 0.72 : 0.58,
              child: Container(
                height: 12,
                margin: EdgeInsetsDirectional.only(
                  start: index.isEven ? 0 : 16,
                  end: index.isEven ? 16 : 0,
                ),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(4),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _CountryName extends StatelessWidget {
  const _CountryName({
    required this.name,
    required this.onTap,
    required this.showEndDivider,
    required this.showBottomDivider,
  });

  final String name;
  final VoidCallback? onTap;
  final bool showEndDivider;
  final bool showBottomDivider;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Semantics(
      button: onTap != null,
      label: name,
      excludeSemantics: true,
      onTap: onTap,
      child: DecoratedBox(
        decoration: _countryGridLines(
          color: context.dividerColor,
          showEndDivider: showEndDivider,
          showBottomDivider: showBottomDivider,
        ),
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: onTap,
            child: Padding(
              padding: EdgeInsetsDirectional.fromSTEB(
                showEndDivider ? 2 : 16,
                12,
                showEndDivider ? 16 : 2,
                12,
              ),
              child: Align(
                alignment: AlignmentDirectional.centerStart,
                child: Text(
                  name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontSize: 15.5,
                    fontWeight: FontWeight.w500,
                    height: 1.3,
                    letterSpacing: -0.1,
                    color: context.textColor,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _RegionChip extends StatelessWidget {
  const _RegionChip({
    required this.label,
    required this.count,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final int count;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final red = Color(AppConstants.ifrcRed);
    final onSelected = theme.colorScheme.onSecondary;
    final foreground = selected ? onSelected : context.textColor;
    final badgeColor = selected
        ? onSelected.withValues(alpha: 0.22)
        : context.navyBackgroundColor(opacity: 0.08);

    return Semantics(
      button: true,
      selected: selected,
      label: '$label, $count',
      excludeSemantics: true,
      onTap: onTap,
      child: Material(
        color: selected ? red : context.cardColor,
        shape: StadiumBorder(
          side: BorderSide(color: selected ? red : context.borderColor),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 40),
            child: Padding(
              padding: const EdgeInsetsDirectional.only(start: 14, end: 8),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    label,
                    style: theme.textTheme.labelLarge?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: foreground,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                    decoration: BoxDecoration(
                      color: badgeColor,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '$count',
                      style: theme.textTheme.labelSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: foreground,
                      ),
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

class _RegionSidebarItem extends StatelessWidget {
  const _RegionSidebarItem({
    required this.label,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final onSelected = theme.colorScheme.onSecondary;
    final foreground = selected ? onSelected : context.textColor;
    final secondary = selected
        ? onSelected.withValues(alpha: 0.85)
        : context.textSecondaryColor;

    return Semantics(
      button: true,
      selected: selected,
      label: '$label, $subtitle',
      excludeSemantics: true,
      onTap: onTap,
      child: Material(
        color: selected ? Color(AppConstants.ifrcRed) : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                    color: foreground,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: theme.textTheme.bodySmall?.copyWith(color: secondary),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _RegionOverviewBanner extends StatelessWidget {
  const _RegionOverviewBanner({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = context.linkOnSurfaceColor;

    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      onTap: onTap,
      child: Material(
        color: context.navyBackgroundColor(opacity: 0.07),
        borderRadius: BorderRadius.circular(14),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
            child: Row(
              children: [
                Icon(Icons.public_rounded, size: 22, color: accent),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    label,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                      color: accent,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Icon(Icons.arrow_forward_rounded, size: 20, color: accent),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
