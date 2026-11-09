import 'dart:async';
import 'dart:convert';
import 'dart:ui';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/public/country_profile.dart';
import '../../providers/shared/language_provider.dart';
import '../../services/api_service.dart';
import '../../services/offline_cache_service.dart';
import '../../services/public_browse_prefetch.dart';
import '../../services/unified_planning_pdf_thumbnail_cache.dart';
import '../../utils/constants.dart';
import '../../utils/network_availability.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/mobile_screen_scaffold.dart';
import '../../widgets/network_logo_image.dart';
import '../../widgets/public/go_operations_section.dart';
import '../../widgets/public/indicator_trend.dart';

/// Native country profile: institutional and emergencies sections.
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

const _heroTextShadows = [
  Shadow(color: Color(0xCC000000), blurRadius: 8),
];

const _initialDocumentYears = 3;
const _institutionalSection = 'institutional';
const _emergenciesSection = 'emergencies';

/// Hosts the Backoffice PDF thumbnail endpoint is willing to fetch.
const _pdfThumbnailHosts = {
  'api.ifrc.org',
  'go.ifrc.org',
  'go-api.ifrc.org',
  'goadmin.ifrc.org',
  'ifrc.org',
  'www.ifrc.org',
  'prddsgofilestorage.blob.core.windows.net',
  'prddsgolocstor01.blob.core.windows.net',
};

/// URLs the thumbnail service already refused this session. Cleared on refresh.
final _pdfThumbMisses = <String>{};

class _CountryDetailScreenState extends State<CountryDetailScreen>
    with SingleTickerProviderStateMixin {
  final ApiService _apiService = sl<ApiService>();
  final PageController _coverController = PageController();
  late final TabController _sectionTabs;
  Timer? _coverTimer;

  CountryProfile? _profile;
  bool _isLoading = true;
  String? _error;
  String? _loadedLanguage;

  String? _selectedKey;
  String _section = _institutionalSection;
  String? _documentType;
  bool _showAllDocumentYears = false;
  bool _documentTiles = true;
  int _coverIndex = 0;
  List<CountryDocument>? _goDocuments;
  bool _goFailed = false;
  int _goRequest = 0;
  GoOperationsSnapshot? _operations;
  bool _operationsFailed = false;
  int _operationsRequest = 0;

  @override
  void initState() {
    super.initState();
    _sectionTabs = TabController(length: 2, vsync: this);
    _sectionTabs.addListener(_onSectionTabChanged);
    // Localizations are not available inside initState.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      UnifiedPlanningPdfThumbnailCache.instance.warmCacheDirectory();
      _load();
    });
  }

  @override
  void dispose() {
    _sectionTabs.removeListener(_onSectionTabChanged);
    _sectionTabs.dispose();
    _coverTimer?.cancel();
    _coverController.dispose();
    super.dispose();
  }

  void _onSectionTabChanged() {
    if (!mounted || _sectionTabs.indexIsChanging) return;
    _selectSection(
      _sectionTabs.index == 0 ? _institutionalSection : _emergenciesSection,
    );
  }

  Future<void> _load() async {
    final loc = AppLocalizations.of(context)!;
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    _loadedLanguage = language;

    _pdfThumbMisses.clear();
    setState(() {
      _isLoading = true;
      _error = null;
      _goDocuments = null;
      _goFailed = false;
      _operations = null;
      _operationsFailed = false;
    });

    try {
      final response = await _apiService.get(
        '${AppConfig.mobileCountryProfileEndpoint}/${Uri.encodeComponent(widget.iso3)}',
        queryParams: {'locale': language},
        includeAuth: false,
        cacheTtl: OfflineCacheService.publicBrowseTtl,
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
      _loadGoDocuments();
      _loadOperations();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = shouldDeferRemoteFetch
            ? loc.offlineNoInternet
            : loc.oopsSomethingWentWrong;
        _isLoading = false;
      });
    }
  }

  Future<void> _loadGoDocuments() async {
    final request = ++_goRequest;
    final iso3 = widget.iso3.trim();
    if (await _showBulkGoDocuments(iso3, request)) return;
    if (shouldDeferRemoteFetch) {
      if (!mounted || request != _goRequest) return;
      setState(() {
        _goDocuments = const [];
        _goFailed = true;
      });
      return;
    }
    try {
      final response = await _apiService.get(
        '${AppConfig.mobileCountryProfileEndpoint}/${Uri.encodeComponent(iso3)}/go-documents',
        includeAuth: false,
        cacheTtl: OfflineCacheService.publicBrowseTtl,
      );
      if (!mounted || request != _goRequest) return;
      if (response.statusCode != 200) {
        if (await _showBulkGoDocuments(iso3, request)) return;
        setState(() {
          _goDocuments = const [];
          _goFailed = true;
        });
        return;
      }
      final decoded = jsonDecode(response.body);
      final data = decoded is Map ? decoded['data'] : null;
      if (data is! Map) {
        if (await _showBulkGoDocuments(iso3, request)) return;
        setState(() {
          _goDocuments = const [];
          _goFailed = true;
        });
        return;
      }
      _showGoDocuments(Map<String, dynamic>.from(data));
    } catch (_) {
      if (!mounted || request != _goRequest) return;
      if (await _showBulkGoDocuments(iso3, request)) return;
      if (!mounted || request != _goRequest) return;
      setState(() {
        _goDocuments = const [];
        _goFailed = true;
      });
    }
  }

  Future<bool> _showBulkGoDocuments(String iso3, int request) async {
    final payload = await cachedGoDocumentsFor(iso3);
    if (!mounted || request != _goRequest || payload == null) return false;
    _showGoDocuments(payload);
    return true;
  }

  void _showGoDocuments(Map<String, dynamic> data) {
    final available = data['available'] != false;
    final documents = data['documents'] is List
        ? (data['documents'] as List)
            .whereType<Map>()
            .map((row) => CountryDocument.fromJson(Map<String, dynamic>.from(row)))
            .where((doc) => doc.url.isNotEmpty)
            .toList(growable: false)
        : const <CountryDocument>[];
    setState(() {
      _goDocuments = documents;
      _goFailed = !available;
    });
  }

  Future<void> _loadOperations() async {
    final request = ++_operationsRequest;
    try {
      final response = await _apiService.get(
        '${AppConfig.mobileCountryProfileEndpoint}/${Uri.encodeComponent(widget.iso3.trim())}/operations',
        includeAuth: false,
        cacheTtl: OfflineCacheService.publicBrowseTtl,
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
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildSectionTabs(loc),
              const SizedBox(height: 20),
              if (_section == _emergenciesSection) ...[
                GoOperationsSection(
                  snapshot: _operations,
                  loading: _operations == null && !_operationsFailed,
                  failed: _operationsFailed,
                  onRetry: _loadOperations,
                ),
                const SizedBox(height: 24),
                ..._buildDocuments(
                  context,
                  theme,
                  loc,
                  profile,
                  operations: true,
                ),
              ] else ...[
                _buildKeyFigures(context, theme, loc, profile),
                const SizedBox(height: 24),
                _buildTrend(context, theme, loc, profile),
                ..._buildTopSectors(context, theme, loc, profile),
                const SizedBox(height: 24),
                ..._buildDocuments(
                  context,
                  theme,
                  loc,
                  profile,
                  operations: false,
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _documentsHeader(
    ThemeData theme,
    AppLocalizations loc, {
    required bool showLayoutToggle,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Expanded(
            child: Text(
              loc.countryDetailDocuments,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
                color: context.navyTextColor,
              ),
            ),
          ),
          if (showLayoutToggle) ...[
            const SizedBox(width: 8),
            _documentLayoutToggle(loc),
          ],
        ],
      ),
    );
  }

  Widget _documentLayoutToggle(AppLocalizations loc) {
    return Material(
      color: Colors.transparent,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: context.borderColor),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _layoutToggleButton(
            selected: _documentTiles,
            icon: Icons.grid_view_rounded,
            tooltip: loc.countryDetailDocumentTiles,
            onPressed: () => setState(() => _documentTiles = true),
          ),
          _layoutToggleButton(
            selected: !_documentTiles,
            icon: Icons.view_list_rounded,
            tooltip: loc.countryDetailDocumentList,
            onPressed: () => setState(() => _documentTiles = false),
          ),
        ],
      ),
    );
  }

  Widget _layoutToggleButton({
    required bool selected,
    required IconData icon,
    required String tooltip,
    required VoidCallback onPressed,
  }) {
    final foreground = selected ? Colors.white : context.textSecondaryColor;
    return Semantics(
      button: true,
      selected: selected,
      child: IconButton(
        tooltip: tooltip,
        visualDensity: VisualDensity.compact,
        padding: const EdgeInsets.all(6),
        constraints: const BoxConstraints(minWidth: 36, minHeight: 32),
        style: IconButton.styleFrom(
          backgroundColor:
              selected ? Color(AppConstants.ifrcRed) : Colors.transparent,
          foregroundColor: foreground,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(7)),
        ),
        onPressed: () {
          if (selected) return;
          HapticFeedback.selectionClick();
          onPressed();
        },
        icon: Icon(icon, size: 18, color: foreground),
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

  BoxDecoration _cardDecoration(BuildContext context) =>
      publicCardDecoration(context);

  // ── Hero ───────────────────────────────────────────────────────────────────

  Widget _buildHero(BuildContext context, CountryProfile profile) {
    final info = profile.country;
    final navy = Color(AppConstants.ifrcNavy);
    final red = Color(AppConstants.ifrcRed);
    final nsName = info.nationalSocietyName?.trim();
    final title = (nsName != null && nsName.isNotEmpty) ? nsName : info.name;
    final logoUrl = info.logoUrl?.trim();

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
          if (logoUrl != null && logoUrl.isNotEmpty)
            Positioned.fill(
              child: IgnorePointer(
                child: _HeroLogo(url: logoUrl),
              ),
            ),
          const IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Color(0x66000000),
                    Colors.transparent,
                    Color(0x73000000),
                    Color(0xE6000000),
                  ],
                  stops: [0, 0.32, 0.55, 1],
                ),
              ),
            ),
          ),
          Positioned(
            left: 16,
            right: 16,
            bottom: 14,
            child: Text(
              title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 26,
                fontWeight: FontWeight.w800,
                height: 1.15,
                shadows: _heroTextShadows,
              ),
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

  Widget _buildSectionTabs(AppLocalizations loc) {
    return Material(
      color: Colors.transparent,
      child: TabBar(
        controller: _sectionTabs,
        indicatorColor: Color(AppConstants.ifrcRed),
        indicatorSize: TabBarIndicatorSize.tab,
        labelColor: Color(AppConstants.ifrcRed),
        unselectedLabelColor: context.textSecondaryColor,
        dividerColor: context.dividerColor,
        labelStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
        unselectedLabelStyle:
            const TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
        tabs: [
          Tab(text: loc.countryDetailInstitutional),
          Tab(text: loc.emergenciesTitle),
        ],
      ),
    );
  }

  // ── Documents ──────────────────────────────────────────────────────────────

  List<Widget> _buildDocuments(
    BuildContext context,
    ThemeData theme,
    AppLocalizations loc,
    CountryProfile profile, {
    required bool operations,
  }) {
    final showingOperations = operations;
    final documents = showingOperations
        ? (_goDocuments ?? const <CountryDocument>[])
        : profile.documents;
    final loadingOperations =
        showingOperations && _goDocuments == null && !_goFailed;
    final types = <String>{
      for (final d in documents)
        if (d.documentType != null && d.documentType!.isNotEmpty)
          d.documentType!,
    }.toList()
      ..sort();

    final filtered = documents
        .where((d) => _documentType == null || d.documentType == _documentType)
        .toList();

    final groups = showingOperations
        ? _emergencyGroups(filtered, loc)
        : _yearGroups(filtered, loc);
    final hiddenUndated = !showingOperations &&
        groups.any((group) => group.undated) &&
        groups.any((group) => !group.undated);
    final datedCount = groups.where((group) => !group.undated).length;
    final hasMoreGroups = showingOperations
        ? groups.length > _initialDocumentYears
        : datedCount > _initialDocumentYears || hiddenUndated;
    final visibleGroups = _showAllDocumentYears || !hasMoreGroups
        ? groups
        : groups.where((group) => !group.undated).take(_initialDocumentYears).toList();

    final showLayoutToggle = documents.isNotEmpty &&
        !loadingOperations &&
        !(showingOperations && _goFailed);
    return [
      _documentsHeader(theme, loc, showLayoutToggle: showLayoutToggle),
      if (loadingOperations)
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 16),
          child: Center(
            child: SizedBox(
              width: 24,
              height: 24,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        )
      else if (showingOperations && _goFailed)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Column(
            children: [
              Text(
                loc.countryDetailOperationsUnavailable,
                style: TextStyle(color: context.textSecondaryColor),
              ),
              TextButton(
                onPressed: _loadGoDocuments,
                child: Text(loc.retry),
              ),
            ],
          ),
        )
      else if (documents.isEmpty)
        Text(
          showingOperations
              ? loc.countryDetailNoOperationsDocuments
              : loc.countryDetailNoDocuments,
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
        for (final group in visibleGroups) ...[
          Padding(
            padding: const EdgeInsets.only(top: 12, bottom: 4),
            child: Text(
              group.label,
              style: theme.textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.w800,
                color: Color(AppConstants.ifrcRed),
              ),
            ),
          ),
          _documentTiles
              ? _buildDocumentGrid(group.documents)
              : _buildDocumentList(group.documents),
        ],
        if (hasMoreGroups && !_showAllDocumentYears)
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

  List<_DocumentGroup> _yearGroups(
    List<CountryDocument> documents,
    AppLocalizations loc,
  ) {
    final byYear = <int?, List<CountryDocument>>{};
    for (final doc in documents) {
      byYear.putIfAbsent(doc.year, () => []).add(doc);
    }
    final years = byYear.keys.toList()
      ..sort((a, b) {
        if (a == null) return 1;
        if (b == null) return -1;
        return b.compareTo(a);
      });
    return [
      for (final year in years)
        _DocumentGroup(
          year?.toString() ?? loc.unknown,
          byYear[year]!,
          undated: year == null,
        ),
    ];
  }

  List<_DocumentGroup> _emergencyGroups(
    List<CountryDocument> documents,
    AppLocalizations loc,
  ) {
    final byKey = <String?, List<CountryDocument>>{};
    final labels = <String?, String>{};
    for (final doc in documents) {
      final code = doc.emergencyCode;
      final name = doc.emergency;
      final key = code ?? name;
      byKey.putIfAbsent(key, () => []).add(doc);
      labels[key] = name ??
          (code != null && !code.startsWith('event:') ? code : loc.unknown);
    }
    final keys = byKey.keys.toList()
      ..sort((a, b) {
        if (a == null) return 1;
        if (b == null) return -1;
        final byYear =
            _newestYear(byKey[b]!).compareTo(_newestYear(byKey[a]!));
        if (byYear != 0) return byYear;
        return labels[a]!.toLowerCase().compareTo(labels[b]!.toLowerCase());
      });
    final labelCounts = <String, int>{};
    for (final key in keys) {
      final label = labels[key]!.toLowerCase();
      labelCounts[label] = (labelCounts[label] ?? 0) + 1;
    }
    return [
      for (final key in keys)
        _DocumentGroup(
          _emergencyHeading(key, labels[key]!, labelCounts),
          byKey[key]!,
          undated: key == null,
        ),
    ];
  }

  String _emergencyHeading(
    String? key,
    String label,
    Map<String, int> labelCounts,
  ) {
    if (key == null || key.startsWith('event:')) return label;
    if ((labelCounts[label.toLowerCase()] ?? 0) < 2) return label;
    return '$label ($key)';
  }

  int _newestYear(List<CountryDocument> documents) {
    var newest = -1;
    for (final doc in documents) {
      final year = doc.year;
      if (year != null && year > newest) newest = year;
    }
    return newest;
  }

  void _selectSection(String section) {
    if (_section == section) return;
    setState(() {
      _section = section;
      _documentType = null;
      _showAllDocumentYears = false;
    });
  }

  Widget _buildDocumentList(List<CountryDocument> docs) {
    return Column(
      children: [
        for (var i = 0; i < docs.length; i++) ...[
          if (i > 0) const SizedBox(height: 8),
          _DocumentListTile(
            key: ValueKey(docs[i].url),
            document: docs[i],
            onOpen: () => _openDocument(docs[i]),
          ),
        ],
      ],
    );
  }

  Widget _buildDocumentGrid(List<CountryDocument> docs) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 10.0;
        final columns = constraints.maxWidth >= 520 ? 3 : 2;
        final width = (constraints.maxWidth - gap * (columns - 1)) / columns;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final doc in docs)
              SizedBox(
                width: width,
                child: _CountryDocumentCard(
                  key: ValueKey(doc.url),
                  document: doc,
                  onOpen: () => _openDocument(doc),
                ),
              ),
          ],
        );
      },
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

class _DocumentGroup {
  const _DocumentGroup(this.label, this.documents, {this.undated = false});

  final String label;
  final List<CountryDocument> documents;
  final bool undated;
}

/// Keeps a text block the height of [maxLines] even when the string wraps less,
/// so cards in the same row stay aligned.
class _ReservedLinesText extends StatelessWidget {
  const _ReservedLinesText({
    required this.text,
    required this.maxLines,
    required this.style,
  });

  final String text;
  final int maxLines;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    final resolved = style ?? DefaultTextStyle.of(context).style;
    final placeholder = List.filled(maxLines, '\u00A0').join('\n');
    return Stack(
      children: [
        ExcludeSemantics(
          child: Text(
            placeholder,
            maxLines: maxLines,
            style: resolved.copyWith(color: Colors.transparent),
          ),
        ),
        Text(
          text,
          maxLines: maxLines,
          overflow: TextOverflow.ellipsis,
          style: resolved,
        ),
      ],
    );
  }
}

bool _sameLabel(String? a, String? b) {
  final left = a?.trim().toLowerCase() ?? '';
  final right = b?.trim().toLowerCase() ?? '';
  return left.isNotEmpty && left == right;
}

/// Compact row for one country document, used when the list layout is selected.
class _DocumentListTile extends StatelessWidget {
  const _DocumentListTile({
    super.key,
    required this.document,
    required this.onOpen,
  });

  final CountryDocument document;
  final VoidCallback onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = document.title.trim().isNotEmpty
        ? document.title.trim()
        : (document.filename ?? '');
    final language = document.language?.trim();
    final type = document.documentType?.trim();
    final meta = [
      if (language != null &&
          language.isNotEmpty &&
          !_sameLabel(language, title))
        language,
      if (type != null &&
          type.isNotEmpty &&
          !_sameLabel(type, language) &&
          !_sameLabel(type, title))
        type,
    ].join(' · ');

    return Material(
      color: context.cardColor,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: context.borderColor),
      ),
      child: InkWell(
        onTap: onOpen,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
          child: Row(
            children: [
              Icon(
                document.isPdf
                    ? Icons.picture_as_pdf_rounded
                    : document.isImage
                        ? Icons.image_rounded
                        : Icons.description_rounded,
                color: Color(AppConstants.ifrcRed),
                size: 22,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(fontWeight: FontWeight.w700),
                    ),
                    if (meta.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        meta,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall
                            ?.copyWith(color: context.textSecondaryColor),
                      ),
                    ],
                  ],
                ),
              ),
              Icon(
                Directionality.of(context) == TextDirection.rtl
                    ? Icons.chevron_left_rounded
                    : Icons.chevron_right_rounded,
                color: context.textSecondaryColor,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Cover tile for one country document. Uses the stored thumbnail when the
/// API sends one, otherwise the first PDF page for IFRC-hosted files.
class _CountryDocumentCard extends StatefulWidget {
  const _CountryDocumentCard({
    super.key,
    required this.document,
    required this.onOpen,
  });

  final CountryDocument document;
  final VoidCallback onOpen;

  @override
  State<_CountryDocumentCard> createState() => _CountryDocumentCardState();
}

class _CountryDocumentCardState extends State<_CountryDocumentCard> {
  Uint8List? _pdfThumb;
  StreamSubscription<String>? _thumbReadySub;

  @override
  void initState() {
    super.initState();
    final url = widget.document.url.trim();
    if (!_wantsServerPdfThumb(widget.document, url)) return;
    final cache = UnifiedPlanningPdfThumbnailCache.instance;
    _pdfThumb = cache.readThumbnailSync(url);
    cache.getThumbnail(url).then((bytes) {
      if (bytes == null || bytes.isEmpty) {
        _pdfThumbMisses.add(url);
        return;
      }
      if (!mounted || identical(bytes, _pdfThumb)) return;
      setState(() => _pdfThumb = bytes);
    });
    _thumbReadySub = cache.thumbnailReady.listen((ready) {
      if (ready.trim() != url || !mounted) return;
      final bytes = cache.readThumbnailSync(url);
      if (bytes != null && bytes.isNotEmpty) {
        setState(() => _pdfThumb = bytes);
      }
    });
  }

  @override
  void dispose() {
    _thumbReadySub?.cancel();
    super.dispose();
  }

  static bool _wantsServerPdfThumb(CountryDocument doc, String url) {
    if (_coverUrl(doc) != null) return false;
    if (!doc.isPdf || url.isEmpty || _pdfThumbMisses.contains(url)) return false;
    final host = Uri.tryParse(url)?.host.toLowerCase() ?? '';
    return _pdfThumbnailHosts.contains(host);
  }

  static String? _coverUrl(CountryDocument doc) {
    final thumb = doc.thumbnail?.trim();
    if (thumb != null && thumb.isNotEmpty) return thumb;
    final url = doc.url.trim();
    if (url.isEmpty) return null;
    if (doc.isPdf) {
      const marker = '/documents/display/';
      if (url.contains(marker)) {
        return url.replaceFirst(marker, '/documents/thumbnail/');
      }
    }
    if (doc.isImage) return url;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final doc = widget.document;
    final title = doc.title.trim().isNotEmpty ? doc.title.trim() : (doc.filename ?? '');
    final language = doc.language?.trim();
    final meta = (language != null && language.isNotEmpty) ? language : doc.documentType;
    final coverUrl = _coverUrl(doc);
    final hasCover = coverUrl != null || (_pdfThumb != null && _pdfThumb!.isNotEmpty);

    return Material(
      color: context.cardColor,
      clipBehavior: Clip.antiAlias,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: context.borderColor),
      ),
      child: InkWell(
        onTap: widget.onOpen,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 156,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  _cover(coverUrl),
                  if (hasCover && doc.isPdf)
                    Positioned(
                      top: 8,
                      right: 8,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.45),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Padding(
                          padding: EdgeInsets.all(4),
                          child: Icon(
                            Icons.picture_as_pdf_rounded,
                            color: Colors.white,
                            size: 14,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 8, 10, 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _ReservedLinesText(
                    text: title,
                    maxLines: 2,
                    style: theme.textTheme.bodyMedium
                        ?.copyWith(fontWeight: FontWeight.w700),
                  ),
                  const SizedBox(height: 2),
                  _ReservedLinesText(
                    text: (meta != null && meta.isNotEmpty) ? meta : '',
                    maxLines: 1,
                    style: theme.textTheme.bodySmall
                        ?.copyWith(color: context.textSecondaryColor),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _cover(String? coverUrl) {
    final fallback = ColoredBox(
      color: Color(AppConstants.ifrcRed).withValues(alpha: 0.08),
      child: Center(
        child: Icon(
          widget.document.isPdf
              ? Icons.picture_as_pdf_rounded
              : widget.document.isImage
                  ? Icons.image_rounded
                  : Icons.description_rounded,
          color: Color(AppConstants.ifrcRed),
          size: 36,
        ),
      ),
    );
    final bytes = _pdfThumb;
    if (coverUrl == null) {
      if (bytes == null || bytes.isEmpty) return fallback;
      return Image.memory(
        bytes,
        fit: BoxFit.cover,
        gaplessPlayback: true,
        errorBuilder: (_, _, _) => fallback,
      );
    }
    return CachedNetworkImage(
      imageUrl: coverUrl,
      fit: BoxFit.cover,
      memCacheWidth: 480,
      placeholder: (_, _) => fallback,
      errorWidget: (_, _, _) =>
          bytes != null && bytes.isNotEmpty
              ? Image.memory(bytes, fit: BoxFit.cover, gaplessPlayback: true)
              : fallback,
    );
  }
}

/// Hero backdrop: the emblem contained inside the banner, over a blurred
/// copy of the same image that covers the banner.
class _HeroLogo extends StatelessWidget {
  const _HeroLogo({required this.url});

  final String url;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth;
        final height = constraints.maxHeight;
        return Stack(
          fit: StackFit.expand,
          children: [
            ClipRect(
              child: Transform.scale(
                scale: 1.12,
                child: ImageFiltered(
                  imageFilter: ImageFilter.blur(sigmaX: 22, sigmaY: 22),
                  child: _logo(
                    width: width,
                    height: height,
                    fit: BoxFit.cover,
                  ),
                ),
              ),
            ),
            _logo(width: width, height: height, fit: BoxFit.contain),
          ],
        );
      },
    );
  }

  Widget _logo({
    required double width,
    required double height,
    required BoxFit fit,
  }) {
    if (isSvgLogoUrl(url)) {
      return SvgPicture.network(
        url,
        width: width,
        height: height,
        fit: fit,
        alignment: Alignment.center,
        placeholderBuilder: (_) => const SizedBox.shrink(),
        errorBuilder: (_, _, _) => const SizedBox.shrink(),
      );
    }
    return CachedNetworkImage(
      imageUrl: url,
      width: width,
      height: height,
      fit: fit,
      alignment: Alignment.center,
      errorWidget: (_, _, _) => const SizedBox.shrink(),
    );
  }
}
