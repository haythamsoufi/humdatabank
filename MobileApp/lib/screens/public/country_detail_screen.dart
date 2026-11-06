import 'dart:async';
import 'dart:convert';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/public/country_profile.dart';
import '../../providers/shared/language_provider.dart';
import '../../services/api_service.dart';
import '../../utils/constants.dart';
import '../../utils/network_availability.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/mobile_screen_scaffold.dart';
import '../../widgets/public/indicator_trend.dart';

/// Native country profile: key figures, trends, indicators and public documents.
class CountryDetailScreen extends StatefulWidget {
  final String iso3;

  /// Shown in the header until the profile has loaded.
  final String? countryName;

  const CountryDetailScreen({
    super.key,
    required this.iso3,
    this.countryName,
  });

  @override
  State<CountryDetailScreen> createState() => _CountryDetailScreenState();
}

const _initialDocumentYears = 3;

class _CountryDetailScreenState extends State<CountryDetailScreen> {
  final ApiService _apiService = sl<ApiService>();
  final PageController _coverController = PageController();
  Timer? _coverTimer;

  CountryProfile? _profile;
  bool _isLoading = true;
  String? _error;
  String? _loadedLanguage;

  String? _selectedKey;
  String? _documentType;
  bool _showAllDocumentYears = false;
  int _coverIndex = 0;

  @override
  void initState() {
    super.initState();
    // Localizations are not available inside initState.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _load();
    });
  }

  @override
  void dispose() {
    _coverTimer?.cancel();
    _coverController.dispose();
    super.dispose();
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
    });

    try {
      final response = await _apiService.get(
        '${AppConfig.mobileCountryProfileEndpoint}/${Uri.encodeComponent(widget.iso3)}',
        queryParams: {'locale': language},
        includeAuth: false,
      );
      if (!mounted) return;

      if (response.statusCode == 404) {
        setState(() {
          _error = loc.countryDetailNotFound;
          _isLoading = false;
        });
        return;
      }
      if (response.statusCode != 200) {
        setState(() {
          _error = loc.oopsSomethingWentWrong;
          _isLoading = false;
        });
        return;
      }

      final decoded = jsonDecode(response.body);
      final data = decoded is Map ? decoded['data'] : null;
      if (data is! Map) {
        setState(() {
          _error = loc.oopsSomethingWentWrong;
          _isLoading = false;
        });
        return;
      }

      final profile = CountryProfile.fromJson(Map<String, dynamic>.from(data));
      setState(() {
        _profile = profile;
        _selectedKey = _firstAvailableKey(profile);
        _isLoading = false;
      });
      _restartCoverTimer(profile.coverImages.length);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = loc.oopsSomethingWentWrong;
        _isLoading = false;
      });
    }
  }

  String? _firstAvailableKey(CountryProfile profile) {
    for (final key in keyIndicatorOrder) {
      if (profile.indicatorByKey(key) != null) return key;
    }
    return null;
  }

  void _restartCoverTimer(int count) {
    _coverTimer?.cancel();
    if (count < 2) return;
    _coverTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (!mounted || !_coverController.hasClients) return;
      _coverController.animateToPage(
        (_coverIndex + 1) % count,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOut,
      );
    });
  }

  Future<void> _openDocument(CountryDocument doc) async {
    final loc = AppLocalizations.of(context)!;
    if (doc.isPdf) {
      await Navigator.of(context).pushNamed(
        AppRoutes.pdfViewer,
        arguments: <String, String>{'url': doc.url, 'title': doc.title},
      );
      return;
    }
    if (doc.isImage) {
      await _showImage(doc);
      return;
    }
    final uri = Uri.tryParse(doc.url);
    var opened = false;
    if (uri != null) {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
    if (!opened && mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(loc.countryDetailOpenFailed)));
    }
  }

  Future<void> _showImage(CountryDocument doc) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) => Dialog(
        backgroundColor: Colors.black,
        insetPadding: const EdgeInsets.all(12),
        child: Stack(
          children: [
            InteractiveViewer(
              child: CachedNetworkImage(
                imageUrl: doc.url,
                fit: BoxFit.contain,
                placeholder: (_, _) =>
                    const Center(child: CircularProgressIndicator()),
                errorWidget: (_, _, _) => const Center(
                  child: Icon(Icons.broken_image_rounded,
                      color: Colors.white54, size: 48),
                ),
              ),
            ),
            Positioned(
              top: 4,
              right: 4,
              child: IconButton(
                icon: const Icon(Icons.close_rounded, color: Colors.white),
                onPressed: () => Navigator.of(dialogContext).pop(),
              ),
            ),
          ],
        ),
      ),
    );
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
      bottomNavigationBar: const AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.noTabSelected,
      ),
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

  Widget _buildContent(
      BuildContext context, ThemeData theme, AppLocalizations loc) {
    final profile = _profile!;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.zero,
      children: [
        _buildHero(context, profile),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildKeyFigures(context, theme, loc, profile),
              const SizedBox(height: 24),
              _buildTrend(context, theme, loc, profile),
              ..._buildTopSectors(context, theme, loc, profile),
              const SizedBox(height: 24),
              ..._buildDocuments(context, theme, loc, profile),
            ],
          ),
        ),
      ],
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

  BoxDecoration _cardDecoration(BuildContext context) =>
      publicCardDecoration(context);

  // ── Hero ───────────────────────────────────────────────────────────────────

  Widget _buildHero(BuildContext context, CountryProfile profile) {
    final info = profile.country;
    final navy = Color(AppConstants.ifrcNavy);
    final red = Color(AppConstants.ifrcRed);
    final subtitle = info.nationalSocietyName;

    return SizedBox(
      height: heroHeight(context),
      child: Stack(
        fit: StackFit.expand,
        children: [
          if (profile.coverImages.isEmpty)
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [navy, red],
                ),
              ),
            )
          else
            PageView.builder(
              controller: _coverController,
              itemCount: profile.coverImages.length,
              onPageChanged: (i) => setState(() => _coverIndex = i),
              itemBuilder: (_, i) => CachedNetworkImage(
                imageUrl: profile.coverImages[i],
                fit: BoxFit.cover,
                placeholder: (_, _) => ColoredBox(color: navy),
                errorWidget: (_, _, _) => ColoredBox(color: navy),
              ),
            ),
          const IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [Color(0x66000000), Colors.transparent, Color(0xCC000000)],
                  stops: [0, 0.4, 1],
                ),
              ),
            ),
          ),
          Positioned(
            left: 16,
            right: 16,
            bottom: 14,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  info.name,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                if (subtitle != null && subtitle.isNotEmpty)
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style:
                        const TextStyle(color: Colors.white70, fontSize: 14),
                  ),
              ],
            ),
          ),
          if (profile.coverImages.length > 1)
            Positioned(
              top: MediaQuery.paddingOf(context).top + 22,
              right: 16,
              child: Row(
                children: [
                  for (var i = 0; i < profile.coverImages.length; i++)
                    Container(
                      width: 6,
                      height: 6,
                      margin: const EdgeInsets.only(left: 4),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color:
                            i == _coverIndex ? Colors.white : Colors.white38,
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  // ── Key figures ────────────────────────────────────────────────────────────

  Widget _buildKeyFigures(BuildContext context, ThemeData theme,
      AppLocalizations loc, CountryProfile profile) {
    const keys = ['volunteers', 'staff', 'branches', 'local_units'];
    Widget tile(String key) {
      final indicator = profile.indicatorByKey(key);
      return Expanded(
        child: KeyFigureTile(
          label: keyIndicatorLabel(key, loc),
          value: indicator == null
              ? '—'
              : formatIndicatorValue(indicator.latestValue),
          caption: indicator?.latestPeriod,
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle(theme, loc.countryDetailKeyFigures),
        Row(children: [tile(keys[0]), const SizedBox(width: 10), tile(keys[1])]),
        const SizedBox(height: 10),
        Row(children: [tile(keys[2]), const SizedBox(width: 10), tile(keys[3])]),
      ],
    );
  }

  // ── Trend chart ────────────────────────────────────────────────────────────

  Widget _buildTrend(BuildContext context, ThemeData theme,
      AppLocalizations loc, CountryProfile profile) {
    final singleKeys = {
      for (final i in profile.indicators)
        if (i.group == null && i.key != null) i.key!,
    };
    final reachChoices = buildReachChoices(profile.indicators, loc);
    final selectable = [
      for (final key in keyIndicatorOrder)
        if (singleKeys.contains(key)) key,
      ...reachChoices.map((c) => c.key),
    ];
    if (selectable.isEmpty) return const SizedBox.shrink();

    final selectedKey = selectable.contains(_selectedKey)
        ? _selectedKey!
        : selectable.first;
    final indicator = profile.indicatorByKey(selectedKey)!;
    final red = Color(AppConstants.ifrcRed);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _sectionTitle(theme, loc.countryDetailKeyIndicators),
        KeyIndicatorSelector(
          singleKeys: singleKeys,
          reachChoices: reachChoices,
          selectedKey: selectedKey,
          onSelected: (key) => setState(() => _selectedKey = key),
        ),
        const SizedBox(height: 12),
        Container(
          padding: const EdgeInsets.fromLTRB(8, 16, 16, 12),
          decoration: _cardDecoration(context),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(left: 8),
                child: Text(
                  '${formatIndicatorValue(indicator.latestValue)}  ·  ${indicator.latestPeriod}',
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.w800,
                    color: red,
                  ),
                ),
              ),
              if (indicator.group != null)
                Padding(
                  padding: const EdgeInsets.only(left: 8, top: 2),
                  child: Text(
                    indicator.name,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: context.textSecondaryColor),
                  ),
                ),
              const SizedBox(height: 12),
              if (indicator.series.length < 2)
                Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    loc.countryDetailNoTrend,
                    style: TextStyle(color: context.textSecondaryColor),
                  ),
                )
              else
                IndicatorTrendChart(series: indicator.series),
            ],
          ),
        ),
      ],
    );
  }

  // ── Top sectors ────────────────────────────────────────────────────────────

  List<Widget> _buildTopSectors(BuildContext context, ThemeData theme,
      AppLocalizations loc, CountryProfile profile) {
    final bySector = <String, List<CountryIndicator>>{};
    for (final indicator in profile.indicators) {
      if (indicator.unit?.trim().toLowerCase() != 'people') continue;
      final sector = indicator.sector;
      if (sector == null || sector.isEmpty) continue;
      bySector.putIfAbsent(sector, () => []).add(indicator);
    }
    if (bySector.isEmpty) return const [];

    // Indicators arrive sorted by latest value, so the first entry is the max.
    final sectors = bySector.entries.toList()
      ..sort((a, b) =>
          b.value.first.latestValue.compareTo(a.value.first.latestValue));

    return [
      const SizedBox(height: 24),
      _sectionTitle(theme, loc.countryDetailTopSectors),
      for (var i = 0; i < sectors.length && i < 3; i++)
        Container(
          margin: const EdgeInsets.only(bottom: 10),
          padding: const EdgeInsets.all(14),
          decoration: _cardDecoration(context),
          child: Row(
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: Color(AppConstants.ifrcRed),
                child: Text(
                  '${i + 1}',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sectors[i].key,
                      style: theme.textTheme.titleSmall
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    Text(
                      sectors[i].value.first.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall
                          ?.copyWith(color: context.textSecondaryColor),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                formatIndicatorValue(sectors[i].value.first.latestValue),
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w800,
                  color: Color(AppConstants.ifrcRed),
                ),
              ),
            ],
          ),
        ),
    ];
  }

  // ── Documents ──────────────────────────────────────────────────────────────

  List<Widget> _buildDocuments(BuildContext context, ThemeData theme,
      AppLocalizations loc, CountryProfile profile) {
    final documents = profile.documents;
    final types = <String>{
      for (final d in documents)
        if (d.documentType != null && d.documentType!.isNotEmpty)
          d.documentType!,
    }.toList()
      ..sort();

    final filtered = documents
        .where((d) => _documentType == null || d.documentType == _documentType)
        .toList();

    final byYear = <int?, List<CountryDocument>>{};
    for (final doc in filtered) {
      byYear.putIfAbsent(doc.year, () => []).add(doc);
    }
    // Newest year first; documents without a year go last.
    final groupYears = byYear.keys.toList()
      ..sort((a, b) {
        if (a == null) return 1;
        if (b == null) return -1;
        return b.compareTo(a);
      });
    final datedYears = groupYears.where((y) => y != null).toList();
    final hasMoreYears = datedYears.length > _initialDocumentYears ||
        (datedYears.isNotEmpty && groupYears.contains(null));
    final visibleYears = _showAllDocumentYears || !hasMoreYears
        ? groupYears
        : datedYears.take(_initialDocumentYears).toList();

    return [
      _sectionTitle(theme, loc.countryDetailDocuments),
      if (documents.isEmpty)
        Text(
          loc.countryDetailNoDocuments,
          style: TextStyle(color: context.textSecondaryColor),
        )
      else ...[
        if (types.length > 1)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                children: [
                  _filterChip(
                    context,
                    label: loc.countryDetailAllTypes,
                    selected: _documentType == null,
                    onTap: () => setState(() => _documentType = null),
                  ),
                  for (final type in types)
                    _filterChip(
                      context,
                      label: type,
                      selected: _documentType == type,
                      onTap: () => setState(() => _documentType = type),
                    ),
                ],
              ),
            ),
          ),
        if (filtered.isEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: Center(
              child: Text(
                loc.noDocumentsFound,
                style: TextStyle(color: context.textSecondaryColor),
              ),
            ),
          ),
        for (final year in visibleYears) ...[
          Padding(
            padding: const EdgeInsets.only(top: 12, bottom: 4),
            child: Text(
              year?.toString() ?? loc.unknown,
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w800,
                color: Color(AppConstants.ifrcRed),
              ),
            ),
          ),
          for (final doc in byYear[year]!) _buildDocumentRow(context, theme, doc),
        ],
        if (hasMoreYears && !_showAllDocumentYears)
          Center(
            child: TextButton(
              onPressed: () => setState(() => _showAllDocumentYears = true),
              child: Text(
                loc.countryDetailLoadMore,
                style: TextStyle(
                  color: Color(AppConstants.ifrcRed),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
      ],
    ];
  }

  Widget _buildDocumentRow(
      BuildContext context, ThemeData theme, CountryDocument doc) {
    final language = doc.language;

    return Column(
      children: [
        ListTile(
          contentPadding: EdgeInsets.zero,
          onTap: () => _openDocument(doc),
          leading: _buildDocumentThumbnail(context, doc),
          title: Text(
            doc.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium
                ?.copyWith(fontWeight: FontWeight.w600),
          ),
          subtitle: language == null || language.isEmpty
              ? null
              : Text(
                  language,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall
                      ?.copyWith(color: context.textSecondaryColor),
                ),
          trailing: Icon(Icons.chevron_right_rounded,
              color: context.textSecondaryColor),
        ),
        Divider(height: 1, color: context.dividerColor),
      ],
    );
  }

  Widget _buildDocumentThumbnail(BuildContext context, CountryDocument doc) {
    const width = 48.0;
    const height = 64.0;
    final fallback = Container(
      width: width,
      height: height,
      alignment: Alignment.center,
      color: Color(AppConstants.ifrcRed).withValues(alpha: 0.08),
      child: Icon(
        doc.isPdf ? Icons.picture_as_pdf_rounded : Icons.description_rounded,
        color: Color(AppConstants.ifrcRed),
      ),
    );
    final thumbnail = doc.thumbnail;
    return ClipRRect(
      borderRadius: BorderRadius.circular(6),
      child: thumbnail == null || thumbnail.isEmpty
          ? fallback
          : CachedNetworkImage(
              imageUrl: thumbnail,
              width: width,
              height: height,
              fit: BoxFit.cover,
              placeholder: (_, __) => fallback,
              errorWidget: (_, __, ___) => fallback,
            ),
    );
  }

  Widget _filterChip(
    BuildContext context, {
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Padding(
      padding: const EdgeInsetsDirectional.only(end: 8),
      child: ChoiceChip(
        label: Text(label),
        selected: selected,
        selectedColor: Color(AppConstants.ifrcRed),
        showCheckmark: false,
        labelStyle: TextStyle(
          color: selected ? Colors.white : context.textColor,
          fontWeight: FontWeight.w600,
          fontSize: 13,
        ),
        onSelected: (_) => onTap(),
      ),
    );
  }
}
