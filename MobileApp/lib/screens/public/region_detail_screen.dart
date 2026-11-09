import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/public/region_profile.dart';
import '../../providers/shared/language_provider.dart';
import '../../services/api_service.dart';
import '../../utils/constants.dart';
import '../../utils/network_availability.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/mobile_screen_scaffold.dart';
import '../../widgets/public/go_operations_section.dart';
import '../../widgets/public/indicator_trend.dart';

/// Native regional analysis: key indicators summed across the region, trend and top countries.
class RegionDetailScreen extends StatefulWidget {
  /// From [AppRoutes.regionSlug].
  final String regionSlug;

  /// Shown in the header until the analysis has loaded.
  final String? regionName;

  const RegionDetailScreen({
    super.key,
    required this.regionSlug,
    this.regionName,
  });

  @override
  State<RegionDetailScreen> createState() => _RegionDetailScreenState();
}

class _RegionDetailScreenState extends State<RegionDetailScreen> {
  final ApiService _apiService = sl<ApiService>();

  RegionProfile? _profile;
  bool _isLoading = true;
  String? _error;
  String? _loadedLanguage;
  String? _selectedKey;
  GoOperationsSnapshot? _operations;
  bool _operationsFailed = false;
  int _operationsRequest = 0;

  @override
  void initState() {
    super.initState();
    // Localizations are not available inside initState.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _load();
    });
  }

  Future<void> _load() async {
    final loc = AppLocalizations.of(context)!;
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    _loadedLanguage = language;

    if (shouldDeferRemoteFetch) {
      setState(() {
        _isLoading = false;
        _error = loc.offlineNoInternet;
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
      _operations = null;
      _operationsFailed = false;
    });

    try {
      final response = await _apiService.get(
        '${AppConfig.mobileRegionProfileEndpoint}/${Uri.encodeComponent(widget.regionSlug)}',
        queryParams: {'locale': language},
        includeAuth: false,
      );
      if (!mounted) return;

      if (response.statusCode == 404) {
        setState(() {
          _error = loc.regionNotFound;
          _isLoading = false;
        });
        return;
      }
      final decoded =
          response.statusCode == 200 ? jsonDecode(response.body) : null;
      final data = decoded is Map ? decoded['data'] : null;
      if (data is! Map) {
        setState(() {
          _error = loc.oopsSomethingWentWrong;
          _isLoading = false;
        });
        return;
      }

      final profile = RegionProfile.fromJson(Map<String, dynamic>.from(data));
      setState(() {
        _profile = profile;
        _selectedKey = _firstAvailableKey(profile);
        _isLoading = false;
      });
      _loadOperations();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = loc.oopsSomethingWentWrong;
        _isLoading = false;
      });
    }
  }

  Future<void> _loadOperations() async {
    final request = ++_operationsRequest;
    try {
      final response = await _apiService.get(
        '${AppConfig.mobileRegionProfileEndpoint}/${Uri.encodeComponent(widget.regionSlug)}/operations',
        includeAuth: false,
      );
      if (!mounted || request != _operationsRequest) return;
      final decoded = response.statusCode == 200 ? jsonDecode(response.body) : null;
      final data = decoded is Map ? decoded['data'] : null;
      if (data is! Map) {
        setState(() => _operationsFailed = true);
        return;
      }
      setState(() {
        _operations = GoOperationsSnapshot.fromJson(Map<String, dynamic>.from(data));
        _operationsFailed = false;
      });
    } catch (_) {
      if (!mounted || request != _operationsRequest) return;
      setState(() => _operationsFailed = true);
    }
  }

  Widget _operationsSection(AppLocalizations loc) {
    return GoOperationsSection(
      title: loc.regionOperationsTitle,
      snapshot: _operations,
      loading: _operations == null && !_operationsFailed,
      failed: _operationsFailed,
      onRetry: _loadOperations,
      showCountries: true,
    );
  }

  String? _firstAvailableKey(RegionProfile profile) {
    for (final key in keyIndicatorOrder) {
      if (profile.indicatorByKey(key) != null) return key;
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final language = context.watch<LanguageProvider>().currentLanguage;

    if (_loadedLanguage != null && _loadedLanguage != language && !_isLoading) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _load();
      });
    }

    return MobileScreenScaffold(
      safeArea: false,
      bottomNavigationBar: AppBottomNavigationBar.shellTabBar,
      body: HeroScreenFrame(
        heroVisible: _profile != null && _error == null && !_isLoading,
        child: ColoredBox(
          color: theme.scaffoldBackgroundColor,
          child: _isLoading
              ? AppLoadingIndicator(message: loc.loading)
              : _error != null
                  ? _buildError(theme, loc)
                  : RefreshIndicator(
                      color: Color(AppConstants.ifrcRed),
                      edgeOffset: MediaQuery.paddingOf(context).top,
                      onRefresh: _load,
                      child: _buildContent(context, theme, loc),
                    ),
        ),
      ),
    );
  }

  Widget _buildHero(BuildContext context, AppLocalizations loc) {
    return Container(
      height: heroHeight(context),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
      alignment: AlignmentDirectional.bottomStart,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(AppConstants.ifrcNavy), Color(AppConstants.ifrcRed)],
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            _profile?.name ?? widget.regionName ?? widget.regionSlug,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 26,
              fontWeight: FontWeight.w800,
            ),
          ),
          Text(
            loc.regionAnalysisTitle,
            style: const TextStyle(color: Colors.white70, fontSize: 14),
          ),
        ],
      ),
    );
  }

  Widget _buildError(ThemeData theme, AppLocalizations loc) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline,
                size: 56, color: theme.colorScheme.error),
            const SizedBox(height: 16),
            Text(
              _error!,
              textAlign: TextAlign.center,
              style: TextStyle(color: theme.colorScheme.error, fontSize: 14),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _load,
              style: ElevatedButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
                foregroundColor: Colors.white,
              ),
              child: Text(loc.retry),
            ),
          ],
        ),
      ),
    );
  }

  Widget _sectionTitle(ThemeData theme, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Text(
        text,
        style: theme.textTheme.titleMedium?.copyWith(
          fontWeight: FontWeight.w700,
          color: context.navyTextColor,
        ),
      ),
    );
  }

  Widget _buildContent(
      BuildContext context, ThemeData theme, AppLocalizations loc) {
    final profile = _profile!;
    final singleKeys = {
      for (final i in profile.indicators)
        if (i.group == null) i.key,
    };
    final reachChoices = buildReachChoices(profile.indicators, loc);
    final selectable = [
      for (final key in keyIndicatorOrder)
        if (singleKeys.contains(key)) key,
      ...reachChoices.map((c) => c.key),
    ];

    if (selectable.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.zero,
        children: [
          _buildHero(context, loc),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 0),
            child: _operationsSection(loc),
          ),
          Padding(
            padding: const EdgeInsets.all(24),
            child: Center(
              child: Text(
                loc.regionNoData,
                style: TextStyle(color: context.textSecondaryColor),
              ),
            ),
          ),
        ],
      );
    }

    final selectedKey =
        selectable.contains(_selectedKey) ? _selectedKey! : selectable.first;
    final selected = profile.indicatorByKey(selectedKey)!;

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      children: [
        _buildHero(context, loc),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _operationsSection(loc),
              const SizedBox(height: 24),
              _buildKeyFigures(profile, loc),
              const SizedBox(height: 24),
              KeyIndicatorSelector(
                singleKeys: singleKeys,
                reachChoices: reachChoices,
                selectedKey: selectedKey,
                onSelected: (key) => setState(() => _selectedKey = key),
              ),
              const SizedBox(height: 12),
              _buildTrend(context, theme, loc, profile, selected),
              const SizedBox(height: 24),
              ..._buildTopCountries(context, theme, loc, selected),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildKeyFigures(RegionProfile profile, AppLocalizations loc) {
    const keys = ['volunteers', 'staff', 'branches', 'local_units'];
    Widget tile(String key) {
      final indicator = profile.indicatorByKey(key);
      return Expanded(
        child: KeyFigureTile(
          label: keyIndicatorLabel(key, loc),
          value: indicator == null
              ? '\u2014'
              : formatIndicatorValue(indicator.latestValue),
          caption: indicator?.latestPeriod,
        ),
      );
    }

    return Column(
      children: [
        Row(children: [tile(keys[0]), const SizedBox(width: 10), tile(keys[1])]),
        const SizedBox(height: 10),
        Row(children: [tile(keys[2]), const SizedBox(width: 10), tile(keys[3])]),
      ],
    );
  }

  Widget _buildTrend(
    BuildContext context,
    ThemeData theme,
    AppLocalizations loc,
    RegionProfile profile,
    RegionIndicator selected,
  ) {
    final red = Color(AppConstants.ifrcRed);
    return Container(
      padding: const EdgeInsets.fromLTRB(8, 16, 16, 12),
      decoration: publicCardDecoration(context),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 8),
            child: Text(
              '${formatIndicatorValue(selected.latestValue)}  \u00b7  ${selected.latestPeriod}',
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w800,
                color: red,
              ),
            ),
          ),
          if (selected.group != null)
            Padding(
              padding: const EdgeInsets.only(left: 8, top: 2),
              child: Text(
                selected.name,
                style: theme.textTheme.bodySmall
                    ?.copyWith(color: context.textSecondaryColor),
              ),
            ),
          Padding(
            padding: const EdgeInsets.only(left: 8, top: 2, bottom: 12),
            child: Text(
              loc.regionCoverage(
                  selected.reportingCountries, profile.countryCount),
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: context.textSecondaryColor),
            ),
          ),
          if (selected.series.length < 2)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                loc.countryDetailNoTrend,
                style: TextStyle(color: context.textSecondaryColor),
              ),
            )
          else
            IndicatorTrendChart(series: selected.series),
        ],
      ),
    );
  }

  List<Widget> _buildTopCountries(BuildContext context, ThemeData theme,
      AppLocalizations loc, RegionIndicator selected) {
    final top = selected.topCountries;
    if (top.isEmpty) return const [];
    final maxValue = top.first.value <= 0 ? 1.0 : top.first.value;

    return [
      _sectionTitle(theme, loc.regionTopCountries),
      for (final country in top)
        InkWell(
          onTap: country.iso3.isEmpty
              ? null
              : () => Navigator.of(context).pushNamed(
                    AppRoutes.countryDetail(country.iso3),
                    arguments: country.name,
                  ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        country.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodyMedium
                            ?.copyWith(fontWeight: FontWeight.w600),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      formatIndicatorValue(country.value),
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: Color(AppConstants.ifrcRed),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: (country.value / maxValue).clamp(0.0, 1.0),
                    minHeight: 6,
                    backgroundColor: context.dividerColor,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      Color(AppConstants.ifrcRed),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
    ];
  }
}
