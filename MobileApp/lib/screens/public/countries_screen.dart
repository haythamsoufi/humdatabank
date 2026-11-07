import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../providers/shared/language_provider.dart';
import '../../services/api_service.dart';
import '../../utils/constants.dart';
import '../../utils/network_availability.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/empty_state.dart';
import '../../widgets/error_state.dart';
import '../../widgets/shimmer_list_placeholder.dart';

class CountriesScreen extends StatefulWidget {
  const CountriesScreen({super.key});

  @override
  State<CountriesScreen> createState() => _CountriesScreenState();
}

class _CountriesScreenState extends State<CountriesScreen> {
  static const double _wideLayoutBreakpoint = 768;

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

  static String _displayName(Map<String, dynamic> country) {
    final localized = (country['localized_name'] as String?)?.trim();
    if (localized != null && localized.isNotEmpty) return localized;
    final name = (country['name'] as String?)?.trim();
    return (name != null && name.isNotEmpty) ? name : 'Unknown';
  }

  static String? _displayNationalSociety(Map<String, dynamic> country) {
    final localized =
        (country['localized_national_society_name'] as String?)?.trim();
    if (localized != null && localized.isNotEmpty) return localized;
    final name = (country['national_society_name'] as String?)?.trim();
    return (name != null && name.isNotEmpty) ? name : null;
  }

  /// Converts an ISO 3166-1 alpha-2 code into its flag emoji, or null when the
  /// code is missing or malformed.
  static String? _flagEmoji(String? iso2) {
    if (iso2 == null || iso2.length != 2) return null;
    final code = iso2.toUpperCase();
    final first = code.codeUnitAt(0);
    final second = code.codeUnitAt(1);
    const a = 0x41;
    const z = 0x5A;
    if (first < a || first > z || second < a || second > z) return null;
    const regionalIndicatorA = 0x1F1E6;
    return String.fromCharCodes([
      regionalIndicatorA + first - a,
      regionalIndicatorA + second - a,
    ]);
  }

  Future<void> _loadCountries({bool refresh = false}) async {
    if (shouldDeferRemoteFetch) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
      return;
    }

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

      final response = await _apiService.get(
        AppConfig.mobileCountryMapEndpoint,
        queryParams: {
          'locale': language,
        },
        includeAuth: false,
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
      final List<Map<String, dynamic>> countries =
          data.map((item) => item as Map<String, dynamic>).toList();

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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(title: localizations.countries),
      body: _buildBody(context, localizations),
    );
  }

  Widget _buildBody(BuildContext context, AppLocalizations localizations) {
    if (_isLoading) {
      return Semantics(
        label: localizations.countriesLoading,
        child: ShimmerListPlaceholder(
          itemCount: 8,
          itemSpacing: 10,
          itemBuilder: (_) => const ShimmerCardPlaceholder(height: 72),
        ),
      );
    }

    if (_hasError) {
      return AppErrorState(
        message: localizations.oopsSomethingWentWrong,
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
    final theme = Theme.of(context);
    final filtered = _getFilteredCountries();
    final textScaler = MediaQuery.textScalerOf(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final cardExtent = math.max(
      72.0,
      textScaler.scale(15) * 1.35 + textScaler.scale(12.5) * 1.35 + 34,
    );

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
          if (filtered.isNotEmpty)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 10),
                child: Semantics(
                  header: true,
                  child: Text(
                    _isSearching
                        ? localizations.countriesCount(filtered.length)
                        : '${_selectedRegion ?? ''} · '
                            '${localizations.countriesCount(filtered.length)}',
                    style: theme.textTheme.labelMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.4,
                      color: context.textSecondaryColor,
                    ),
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
                gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 440,
                  mainAxisExtent: cardExtent,
                  crossAxisSpacing: 10,
                  mainAxisSpacing: 10,
                ),
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    final country = filtered[index];
                    final name = _displayName(country);
                    final iso3 = country['iso3'] as String?;
                    final nationalSociety = _displayNationalSociety(country);
                    return _CountryCard(
                      name: name,
                      subtitle: nationalSociety,
                      flag: _flagEmoji(country['iso2'] as String?),
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

class _CountryCard extends StatelessWidget {
  const _CountryCard({
    required this.name,
    required this.onTap,
    this.subtitle,
    this.flag,
  });

  final String name;
  final String? subtitle;
  final String? flag;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(14);

    return Semantics(
      button: onTap != null,
      label: subtitle == null ? name : '$name, $subtitle',
      excludeSemantics: true,
      onTap: onTap,
      child: Material(
        color: context.cardColor,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: BorderSide(color: context.borderColor),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
            child: Row(
              children: [
                Container(
                  width: 44,
                  height: 44,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: context.navyBackgroundColor(opacity: 0.07),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: flag != null
                      ? Text(flag!, style: const TextStyle(fontSize: 24))
                      : Icon(
                          Icons.public_rounded,
                          size: 22,
                          color: context.navyIconColor,
                        ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          height: 1.3,
                          color: context.textColor,
                        ),
                      ),
                      if (subtitle != null)
                        Text(
                          subtitle!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontSize: 12.5,
                            height: 1.3,
                            color: context.textSecondaryColor,
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                Icon(
                  Icons.chevron_right_rounded,
                  size: 22,
                  color: context.textSecondaryColor.withValues(alpha: 0.7),
                ),
              ],
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
