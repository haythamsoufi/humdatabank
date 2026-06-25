import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../config/fdrs_constants.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/disaggregation/disaggregation_overview.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../providers/shared/tab_customization_provider.dart';
import '../../services/disaggregation_data_service.dart';
import '../../utils/navigation_helper.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_navigation_drawer.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/disaggregation/disagg_chart_panel.dart';
import '../../widgets/disaggregation/disagg_filter_sheet.dart';
import '../../widgets/disaggregation/disagg_summary_cards.dart';
import '../../widgets/error_state.dart';
import '../../widgets/ios_button.dart';
import '../../widgets/loading_indicator.dart';

class DisaggregationAnalysisScreen extends StatefulWidget {
  const DisaggregationAnalysisScreen({super.key});

  @override
  State<DisaggregationAnalysisScreen> createState() =>
      _DisaggregationAnalysisScreenState();
}

class _DisaggregationAnalysisScreenState
    extends State<DisaggregationAnalysisScreen>
    with AutomaticKeepAliveClientMixin {
  final DisaggregationDataService _service = sl<DisaggregationDataService>();

  DisaggregationFilters _filters = const DisaggregationFilters(
    indicatorBankId: FdrsConstants.indicatorPeopleReached,
  );
  DisaggregationChartTab _chartTab = DisaggregationChartTab.bySex;

  List<String> _periods = const [];
  List<DisaggregationCountryOption> _countries = const [];
  DisaggregationOverview? _overview;
  bool _loading = true;
  String? _error;
  String? _lastLanguage;
  bool? _lastAuthenticated;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _bootstrap());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    final authenticated =
        Provider.of<AuthProvider>(context, listen: false).isAuthenticated;
    final shouldReload = _lastLanguage != null &&
        (_lastLanguage != language || _lastAuthenticated != authenticated);
    if (shouldReload) {
      _lastLanguage = language;
      _lastAuthenticated = authenticated;
      if (!authenticated && _filters.countryId != null) {
        _filters = _filters.copyWith(clearCountry: true);
      }
      _bootstrap();
    } else {
      _lastLanguage ??= language;
      _lastAuthenticated ??= authenticated;
    }
  }

  Future<void> _bootstrap() async {
    if (!mounted) return;
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    _lastLanguage = language;
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final results = await Future.wait([
        _service.listPeriods(),
        _service.listCountries(locale: language),
        _service.loadOverview(locale: language, filters: _filters),
      ]);
      if (!mounted) return;
      setState(() {
        _periods = results[0] as List<String>;
        _countries = results[1] as List<DisaggregationCountryOption>;
        _overview = results[2] as DisaggregationOverview;
        _loading = false;
        _syncChartTabForAccess(_overview!);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _reloadOverview() async {
    if (!mounted) return;
    final language =
        Provider.of<LanguageProvider>(context, listen: false).currentLanguage;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final overview =
          await _service.loadOverview(locale: language, filters: _filters);
      if (!mounted) return;
      setState(() {
        _overview = overview;
        _loading = false;
        _syncChartTabForAccess(overview);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    }
  }

  Future<void> _openFilters(
    AppLocalizations loc,
    ThemeData theme,
    bool showCountryFilter,
  ) async {
    final result = await showDisaggFilterSheet(
      context: context,
      loc: loc,
      theme: theme,
      initial: _filters,
      periods: _periods,
      countries: _countries,
      showCountryFilter: showCountryFilter,
    );
    if (result == null || !mounted) return;
    setState(() => _filters = result);
    await     _reloadOverview();
  }

  void _syncChartTabForAccess(DisaggregationOverview overview) {
    if (overview.countryDetailsAvailable) {
      if (_chartTab == DisaggregationChartTab.byRegion) {
        _chartTab = DisaggregationChartTab.byCountry;
      }
      return;
    }
    if (_chartTab == DisaggregationChartTab.byCountry) {
      _chartTab = DisaggregationChartTab.byRegion;
    }
  }

  void _clearFilters({required bool showCountryFilter}) {
    setState(() {
      _filters = const DisaggregationFilters(
        indicatorBankId: FdrsConstants.indicatorPeopleReached,
      );
    });
    _reloadOverview();
  }

  bool _isStandaloneScreen(BuildContext context) {
    final route = ModalRoute.of(context);
    final routeName = route?.settings.name;
    if (routeName == AppRoutes.disaggregationAnalysis) return true;
    if (routeName == null || routeName == AppRoutes.dashboard) return false;
    return Navigator.of(context).canPop();
  }

  void _showCountriesSheet(BuildContext context, ThemeData theme) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (sheetContext) {
        return Container(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.9,
          ),
          decoration: BoxDecoration(
            color: theme.scaffoldBackgroundColor,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
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
                    horizontal: 24,
                    vertical: 16,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        AppLocalizations.of(context)!.countries,
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                        ),
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

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isStandalone = _isStandaloneScreen(context);
    final bottomPad = MediaQuery.viewPaddingOf(context).bottom + 16;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.disaggregationAnalysis,
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
            icon: const Icon(Icons.refresh),
            tooltip: loc.disaggRetry,
            onPressed: _loading ? null : _reloadOverview,
          ),
        ],
      ),
      drawer: AppNavigationDrawer(
        activeScreen: ActiveDrawerScreen.home,
        onShowCountriesSheet: () => _showCountriesSheet(context, theme),
      ),
      body: RefreshIndicator(
        onRefresh: _bootstrap,
        child: _buildBody(loc, theme, bottomPad),
      ),
      bottomNavigationBar: isStandalone
          ? Consumer2<AuthProvider, TabCustomizationProvider>(
              builder: (context, auth, tabs, _) {
                final user = auth.user;
                final chatbot = user?.chatbotEnabled ?? false;
                final analysisIndex = tabs.indexOfTab(
                  TabIds.analysis,
                  isAdmin: user?.isAdmin ?? false,
                  isAuthenticated: auth.isAuthenticated,
                  isFocalPoint: user?.isFocalPoint ?? false,
                  chatbotEnabled: chatbot,
                );
                return AppBottomNavigationBar(
                  currentIndex: analysisIndex >= 0 ? analysisIndex : 0,
                  onTap: (index) {
                    NavigationHelper.popToMainThenOpenAiIfNeeded(
                      context,
                      index,
                    );
                  },
                );
              },
            )
          : null,
    );
  }

  Widget _buildBody(AppLocalizations loc, ThemeData theme, double bottomPad) {
    if (_loading && _overview == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: const [
          SizedBox(height: 120),
          Center(child: AppLoadingIndicator()),
        ],
      );
    }

    if (_error != null && _overview == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: EdgeInsets.only(bottom: bottomPad),
        children: [
          const SizedBox(height: 48),
          AppErrorState(
            title: loc.disaggLoadError,
            message: _error,
            onRetry: _bootstrap,
            retryLabel: loc.disaggRetry,
            retryStyle: AppErrorRetryStyle.materialFilled,
          ),
        ],
      );
    }

    final overview = _overview;
    if (overview == null) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          const SizedBox(height: 48),
          Center(child: Text(loc.disaggNoData)),
        ],
      );
    }

    return CustomScrollView(
      physics: const AlwaysScrollableScrollPhysics(
        parent: BouncingScrollPhysics(),
      ),
      slivers: [
        SliverToBoxAdapter(child: DisaggHeroHeader(loc: loc)),
        if (!overview.countryDetailsAvailable)
          SliverToBoxAdapter(
            child: DisaggPublicInsightsBanner(
              loc: loc,
              onLogin: Provider.of<AuthProvider>(context, listen: false)
                      .isAuthenticated
                  ? null
                  : () => Navigator.of(context).pushNamed(AppRoutes.login),
            ),
          ),
        SliverToBoxAdapter(
          child: DisaggFilterBar(
            filters: _filters,
            periods: _periods,
            countries: _countries,
            loc: loc,
            showCountryFilter: overview.countryDetailsAvailable,
            onOpenFilters: () => _openFilters(
              loc,
              theme,
              overview.countryDetailsAvailable,
            ),
            onClearFilters: () => _clearFilters(
              showCountryFilter: overview.countryDetailsAvailable,
            ),
          ),
        ),
        if (_loading)
          const SliverToBoxAdapter(
            child: LinearProgressIndicator(minHeight: 2),
          ),
        SliverToBoxAdapter(
          child: DisaggSummaryCards(overview: overview, loc: loc),
        ),
        SliverToBoxAdapter(
          child: DisaggTabSelector(
            selected: _chartTab,
            onChanged: (tab) => setState(() => _chartTab = tab),
            loc: loc,
            countryDetailsAvailable: overview.countryDetailsAvailable,
          ),
        ),
        SliverToBoxAdapter(
          child: DisaggChartPanel(
            overview: overview,
            tab: _chartTab,
            loc: loc,
          ),
        ),
        if (overview.countryDetailsAvailable)
          SliverToBoxAdapter(
            child: DisaggCountryCoverageList(
              items: overview.byCountry,
              loc: loc,
            ),
          )
        else
          SliverToBoxAdapter(
            child: DisaggRegionCoverageList(
              items: overview.byRegion,
              loc: loc,
            ),
          ),
        SliverPadding(padding: EdgeInsets.only(bottom: bottomPad)),
      ],
    );
  }
}
