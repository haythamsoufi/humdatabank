import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../models/indicator_bank/indicator.dart';
import '../../models/indicator_bank/sector.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../widgets/app_navigation_drawer.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/ios_button.dart';
import '../../config/routes.dart';
import '../../utils/navigation_helper.dart';
import '../../l10n/app_localizations.dart';

class IndicatorBankScreen extends StatefulWidget {
  const IndicatorBankScreen({super.key});

  @override
  State<IndicatorBankScreen> createState() => _IndicatorBankScreenState();
}

class _IndicatorBankScreenState extends State<IndicatorBankScreen> {
  final TextEditingController _searchController = TextEditingController();
  String? _lastLanguage;

  // Propose form controllers
  final _proposeFormKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _indicatorNameController = TextEditingController();
  final _definitionController = TextEditingController();
  final _typeController = TextEditingController();
  final _unitController = TextEditingController();
  final _sectorPrimaryController = TextEditingController();
  final _sectorSecondaryController = TextEditingController();
  final _sectorTertiaryController = TextEditingController();
  final _subSectorPrimaryController = TextEditingController();
  final _subSectorSecondaryController = TextEditingController();
  final _subSectorTertiaryController = TextEditingController();
  final _relatedProgramsController = TextEditingController();
  final _reasonController = TextEditingController();
  final _additionalNotesController = TextEditingController();
  bool _emergencyContext = false;
  bool _submittingProposal = false;
  bool _submitSuccess = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
    });
    _searchController.addListener(_onSearchChanged);
  }

  void _loadData({bool forceRefresh = false}) {
    final indicatorProvider =
        Provider.of<IndicatorBankProvider>(context, listen: false);
    final languageProvider =
        Provider.of<LanguageProvider>(context, listen: false);
    indicatorProvider.loadData(
      locale: languageProvider.currentLanguage,
      forceRefresh: forceRefresh,
    );
  }

  @override
  void dispose() {
    _searchController.dispose();
    _nameController.dispose();
    _emailController.dispose();
    _indicatorNameController.dispose();
    _definitionController.dispose();
    _typeController.dispose();
    _unitController.dispose();
    _sectorPrimaryController.dispose();
    _sectorSecondaryController.dispose();
    _sectorTertiaryController.dispose();
    _subSectorPrimaryController.dispose();
    _subSectorSecondaryController.dispose();
    _subSectorTertiaryController.dispose();
    _relatedProgramsController.dispose();
    _reasonController.dispose();
    _additionalNotesController.dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    final provider = Provider.of<IndicatorBankProvider>(context, listen: false);
    provider.setSearchTerm(_searchController.text);
    if (_searchController.text.isNotEmpty && provider.viewMode == 'grid') {
      provider.setViewMode('table');
    }
  }

  void _showCountriesSheet(BuildContext context, ThemeData theme) {
    final localizations = AppLocalizations.of(context)!;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
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
                // Handle bar
                Container(
                  margin: const EdgeInsets.only(
                    top: IOSSpacing.md - 4,
                    bottom: IOSSpacing.sm,
                  ),
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: theme.dividerColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
                // Title
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: IOSSpacing.xl,
                    vertical: IOSSpacing.md,
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        localizations.countries,
                        style: theme.textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: theme.colorScheme.onSurface,
                        ),
                      ),
                      IOSIconButton(
                        icon: Icons.close,
                        onPressed: () => Navigator.pop(bottomSheetContext),
                        tooltip: localizations.close,
                        semanticLabel: localizations.close,
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                // Countries widget
                const Expanded(
                  child: CountriesWidget(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  bool _isStandaloneScreen(BuildContext context) {
    // Check if this screen is navigated to directly (not as a tab in MainNavigationScreen)
    // When used as a tab, it's embedded in MainNavigationScreen (route name is dashboard or null)
    // When navigated directly via pushNamed, it has a route name matching AppRoutes.indicatorBank

    final route = ModalRoute.of(context);
    final routeName = route?.settings.name;

    // If route name matches this screen's route exactly, we're definitely standalone
    if (routeName == AppRoutes.indicatorBank) {
      return true;
    }

    // If route name is null or dashboard, we're a tab (embedded in MainNavigationScreen)
    // MainNavigationScreen wraps tabs and has its own bottomNavigationBar
    if (routeName == null || routeName == AppRoutes.dashboard) {
      return false;
    }

    // For any other route name, check if we can pop
    // If we can pop, we were navigated to directly (standalone)
    // If we can't pop, we're at the root (likely a tab)
    return Navigator.of(context).canPop();
  }

  String _getSectorIcon(String sectorName) {
    final name = sectorName.toLowerCase();
    if (name.contains('health')) return '🏥';
    if (name.contains('shelter')) return '🏠';
    if (name.contains('water') || name.contains('sanitation')) return '💧';
    if (name.contains('food') || name.contains('nutrition')) return '🍽️';
    if (name.contains('education')) return '📚';
    if (name.contains('protection')) return '🛡️';
    if (name.contains('livelihood')) return '💼';
    if (name.contains('coordination')) return '🤝';
    if (name.contains('emergency')) return '🚨';
    if (name.contains('disaster')) return '⚠️';
    if (name.contains('environment')) return '🌱';
    if (name.contains('migration')) return '🚶';
    if (name.contains('community')) return '👥';
    return '📊';
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    return Consumer2<LanguageProvider, IndicatorBankProvider>(
      builder: (context, languageProvider, indicatorProvider, child) {
        // Reload data when language changes
        final currentLanguage = languageProvider.currentLanguage;
        if (_lastLanguage != currentLanguage) {
          _lastLanguage = currentLanguage;
          WidgetsBinding.instance.addPostFrameCallback((_) {
            indicatorProvider.loadData(
              locale: currentLanguage,
              forceRefresh: true,
            );
          });
        }

        final theme = Theme.of(context);

        return Scaffold(
          primary: true,
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: localizations.indicatorBankTitle,
            leading: Builder(
              builder: (BuildContext scaffoldContext) {
                return IOSIconButton(
                  icon: Icons.menu,
                  onPressed: () {
                    Scaffold.of(scaffoldContext).openDrawer();
                  },
                  tooltip: localizations.navigation,
                  semanticLabel: localizations.navigation,
                  semanticHint: localizations.navigation,
                );
              },
            ),
            actions: [
              IconButton(
                icon: const Icon(Icons.add),
                color: Color(AppConstants.ifrcRed),
                tooltip: localizations.indicatorBankProposeNew,
                onPressed: () {
                  _resetProposeForm();
                  _showProposeIndicatorModal();
                },
              ),
            ],
          ),
          drawer: AppNavigationDrawer(
            activeScreen: ActiveDrawerScreen.indicatorBank,
            onShowCountriesSheet: () => _showCountriesSheet(context, theme),
          ),
          body: ColoredBox(
            color: theme.scaffoldBackgroundColor,
            child: SafeArea(
              top: false,
              bottom: false,
              child: Builder(
                builder: (context) {
                  final provider = indicatorProvider;
                  if (provider.isLoading &&
                      provider.allIndicators.isEmpty) {
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
                            localizations.indicatorBankLoading,
                            style: IOSTextStyle.subheadline(context).copyWith(
                              color: context.textSecondaryColor,
                            ),
                          ),
                        ],
                      ),
                    );
                  }

                  if (provider.error != null &&
                      provider.allIndicators.isEmpty) {
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
                              localizations.indicatorBankError,
                              style: TextStyle(
                                fontSize: 18,
                                fontWeight: FontWeight.w600,
                                color: context.textColor,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              provider.error!,
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Color(AppConstants.textSecondary),
                                fontSize: 14,
                              ),
                            ),
                            const SizedBox(height: 24),
                            OutlinedButton.icon(
                              onPressed: () {
                                provider.loadData(
                                  locale: languageProvider.currentLanguage,
                                  forceRefresh: true,
                                );
                              },
                              icon: const Icon(Icons.refresh, size: 18),
                              label: Text(localizations.retry),
                              style: OutlinedButton.styleFrom(
                                foregroundColor:
                                    Color(AppConstants.ifrcRed),
                                side: BorderSide(
                                  color: Color(AppConstants.ifrcRed),
                                ),
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 24,
                                  vertical: 12,
                                ),
                                shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }

                  return RefreshIndicator(
                    onRefresh: () => provider.loadData(
                      locale: languageProvider.currentLanguage,
                      forceRefresh: true,
                    ),
                    color: Color(AppConstants.ifrcRed),
                    child: CustomScrollView(
                      slivers: [
                        // Header
                        SliverToBoxAdapter(
                          child: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal:
                                  MediaQuery.of(context).size.width > 600
                                      ? 32
                                      : 20,
                              vertical: 20,
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Search and controls
                                _buildSearchAndControls(provider),
                              ],
                            ),
                          ),
                        ),
                        // Content
                        if (provider.viewMode == 'grid')
                          _buildGridView(provider)
                        else
                          _buildTableView(provider),
                      ],
                    ),
                  );
                },
              ),
            ),
          ),
          bottomNavigationBar: _isStandaloneScreen(context)
              ? AppBottomNavigationBar(
                  currentIndex: 2, // Home tab highlighted
                  onTap: (index) {
                    NavigationHelper.popToMainThenOpenAiIfNeeded(
                        context, index);
                  },
                )
              : null,
        );
      },
    );
  }

  Widget _buildSearchAndControls(IndicatorBankProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Column(
      children: [
        // Search bar
        TextField(
          controller: _searchController,
          decoration: InputDecoration(
            hintText: localizations.indicatorBankSearchPlaceholder,
            prefixIcon: const Icon(Icons.search,
                color: Color(AppConstants.textSecondary)),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
              borderSide: const BorderSide(
                color: Color(AppConstants.borderColor),
              ),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
              borderSide: const BorderSide(
                color: Color(AppConstants.borderColor),
              ),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
              borderSide: BorderSide(
                color: Color(AppConstants.ifrcRed),
                width: 2,
              ),
            ),
            filled: true,
            fillColor: context.lightSurfaceColor,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: 16,
              vertical: 16,
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Controls row: M3 segmented view toggle + optional filters
        LayoutBuilder(
          builder: (context, constraints) {
            final compact = constraints.maxWidth < 360;
            final brandRed = Color(AppConstants.ifrcRed);
            final selectedBg = brandRed.withValues(alpha: context.isDarkTheme ? 0.22 : 0.12);
            return Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Expanded(
                  child: SegmentedButton<String>(
                    showSelectedIcon: false,
                    emptySelectionAllowed: false,
                    style: ButtonStyle(
                      visualDensity: VisualDensity.compact,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      padding: WidgetStateProperty.all(
                        EdgeInsets.symmetric(
                          horizontal: compact ? 6 : 10,
                          vertical: compact ? 8 : 10,
                        ),
                      ),
                      side: WidgetStateProperty.resolveWith((states) {
                        final outline = theme.colorScheme.outlineVariant
                            .withValues(alpha: context.isDarkTheme ? 0.55 : 0.45);
                        if (states.contains(WidgetState.selected)) {
                          return BorderSide(color: brandRed.withValues(alpha: 0.65), width: 1);
                        }
                        return BorderSide(color: outline, width: 1);
                      }),
                      backgroundColor: WidgetStateProperty.resolveWith((states) {
                        if (states.contains(WidgetState.selected)) {
                          return selectedBg;
                        }
                        return theme.colorScheme.surfaceContainerLow;
                      }),
                      foregroundColor: WidgetStateProperty.resolveWith((states) {
                        if (states.contains(WidgetState.selected)) {
                          return brandRed;
                        }
                        return theme.colorScheme.onSurfaceVariant;
                      }),
                    ),
                    segments: [
                      ButtonSegment<String>(
                        value: 'grid',
                        tooltip: localizations.indicatorBankGridView,
                        icon: Icon(
                          Icons.grid_view_rounded,
                          size: compact ? 20 : 18,
                        ),
                        label: compact
                            ? null
                            : Text(
                                localizations.indicatorBankGridView,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: theme.textTheme.labelMedium,
                              ),
                      ),
                      ButtonSegment<String>(
                        value: 'table',
                        tooltip: localizations.indicatorBankTableView,
                        icon: Icon(
                          Icons.view_list_rounded,
                          size: compact ? 20 : 18,
                        ),
                        label: compact
                            ? null
                            : Text(
                                localizations.indicatorBankTableView,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: theme.textTheme.labelMedium,
                              ),
                      ),
                    ],
                    selected: {provider.viewMode},
                    onSelectionChanged: (Set<String> next) {
                      if (next.isEmpty) return;
                      provider.setViewMode(next.first);
                    },
                  ),
                ),
                if (provider.viewMode == 'table') ...[
                  const SizedBox(width: 12),
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () => _openIndicatorBankFilters(provider),
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          vertical: compact ? 10 : 12,
                          horizontal: compact ? 12 : 14,
                        ),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.surfaceContainerLow,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: theme.colorScheme.outlineVariant
                                .withValues(alpha: context.isDarkTheme ? 0.55 : 0.45),
                            width: 1,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.filter_list,
                              size: 18,
                              color: theme.colorScheme.onSurface,
                            ),
                            if (!compact) ...[
                              const SizedBox(width: 6),
                              Text(
                                localizations.indicatorBankShowFilters,
                                overflow: TextOverflow.ellipsis,
                                maxLines: 1,
                                style: TextStyle(
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                  color: theme.colorScheme.onSurface,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            );
          },
        ),
      ],
    );
  }

  Future<void> _openIndicatorBankFilters(IndicatorBankProvider provider) async {
    final loc = AppLocalizations.of(context)!;
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (sheetContext, setModalState) {
        return AdminFilterPanel(
          title: loc.indicatorBankFilters,
          leadingIcon: Icons.filter_list,
          surfaceCard: false,
          actions: AdminFilterPanelActions(
            applyLabel: loc.indicatorBankApplyFilters,
            clearLabel: loc.indicatorBankClearAll,
            onApply: () async {
              await provider.applyFilters();
              if (!sheetContext.mounted) return;
              Navigator.of(sheetContext).pop();
            },
            onClear: () {
              provider.clearFilters();
              _searchController.clear();
              if (mounted) Navigator.of(sheetContext).pop();
            },
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              DropdownButtonFormField<String>(
                key: ValueKey<String>('ib_type_${provider.selectedType}'),
                initialValue: provider.selectedType.isEmpty
                    ? null
                    : provider.selectedType,
                decoration: InputDecoration(
                  labelText: loc.indicatorBankFilterType,
                ),
                isExpanded: true,
                items: [
                  DropdownMenuItem<String>(
                    value: null,
                    child: Text(
                      loc.indicatorBankFilterTypeAll,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  ...provider.types.map(
                    (type) => DropdownMenuItem<String>(
                      value: type,
                      child: Text(type, overflow: TextOverflow.ellipsis),
                    ),
                  ),
                ],
                onChanged: (value) {
                  provider.setSelectedType(value ?? '');
                  setModalState(() {});
                },
              ),
              AdminFilterPanel.fieldGap,
              Builder(
                builder: (context) {
                  final uniqueSectors = <String, Sector>{};
                  for (final sector in provider.sectors) {
                    if (!uniqueSectors.containsKey(sector.name)) {
                      uniqueSectors[sector.name] = sector;
                    }
                  }
                  final sectorList = uniqueSectors.values.toList();

                  return DropdownButtonFormField<String>(
                    key: ValueKey<String>('ib_sector_${provider.selectedSector}'),
                    initialValue: provider.selectedSector.isEmpty
                        ? null
                        : (sectorList.any((s) => s.name == provider.selectedSector)
                            ? provider.selectedSector
                            : null),
                    decoration: InputDecoration(
                      labelText: loc.indicatorBankFilterSector,
                    ),
                    isExpanded: true,
                    items: [
                      DropdownMenuItem<String>(
                        value: null,
                        child: Text(
                          loc.indicatorBankFilterSectorAll,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      ...sectorList.map(
                        (sector) => DropdownMenuItem<String>(
                          value: sector.name,
                          child: Text(
                            sector.displayName,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      provider.setSelectedSector(value ?? '');
                      setModalState(() {});
                    },
                  );
                },
              ),
              AdminFilterPanel.fieldGap,
              Builder(
                builder: (context) {
                  final allSubsectors = provider.sectors
                      .expand((s) => s.subsectors)
                      .where(
                        (sub) =>
                            provider.selectedSector.isEmpty ||
                            sub.sectorId ==
                                provider.sectors
                                    .firstWhere(
                                      (s) => s.name == provider.selectedSector,
                                      orElse: () => provider.sectors.first,
                                    )
                                    .id,
                      )
                      .toList();

                  final uniqueSubsectors = <String, SubSector>{};
                  for (final subsector in allSubsectors) {
                    if (!uniqueSubsectors.containsKey(subsector.name)) {
                      uniqueSubsectors[subsector.name] = subsector;
                    }
                  }
                  final subsectorList = uniqueSubsectors.values.toList();

                  return DropdownButtonFormField<String>(
                    key: ValueKey<String>(
                      'ib_sub_${provider.selectedSector}_${provider.selectedSubSector}',
                    ),
                    initialValue: provider.selectedSubSector.isEmpty
                        ? null
                        : (subsectorList.any(
                                (s) => s.name == provider.selectedSubSector)
                            ? provider.selectedSubSector
                            : null),
                    decoration: InputDecoration(
                      labelText: loc.indicatorBankFilterSubsector,
                    ),
                    isExpanded: true,
                    items: [
                      DropdownMenuItem<String>(
                        value: null,
                        child: Text(
                          loc.indicatorBankFilterSubsectorAll,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      ...subsectorList.map(
                        (subsector) => DropdownMenuItem<String>(
                          value: subsector.name,
                          child: Text(
                            subsector.displayName,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                    ],
                    onChanged: (value) {
                      provider.setSelectedSubSector(value ?? '');
                      setModalState(() {});
                    },
                  );
                },
              ),
              AdminFilterPanel.fieldGap,
              DropdownButtonFormField<String>(
                key: ValueKey<String>(
                  'ib_arch_${provider.archived}',
                ),
                initialValue: provider.archived ? 'all' : 'active',
                decoration: InputDecoration(
                  labelText: loc.indicatorBankFilterStatus,
                ),
                isExpanded: true,
                items: [
                  DropdownMenuItem<String>(
                    value: 'active',
                    child: Text(
                      loc.indicatorBankFilterStatusActive,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  DropdownMenuItem<String>(
                    value: 'all',
                    child: Text(
                      loc.indicatorBankFilterStatusAll,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                onChanged: (value) {
                  provider.setArchived(value == 'all');
                  setModalState(() {});
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildGridView(IndicatorBankProvider provider) {
    final sectorsWithCounts = provider.sectorsWithCounts
        .where((s) => provider.getSectorIndicatorCount(s.name) > 0)
        .toList();

    final localizations = AppLocalizations.of(context)!;

    if (sectorsWithCounts.isEmpty) {
      return SliverFillRemaining(
        hasScrollBody: false,
        child: Center(
          child: Text(
            localizations.indicatorBankNoSectors,
            style: const TextStyle(
              fontSize: 16,
              color: Color(AppConstants.textSecondary),
            ),
          ),
        ),
      );
    }

    return SliverPadding(
      padding: EdgeInsets.symmetric(
        horizontal: MediaQuery.of(context).size.width > 600 ? 32 : 20,
      ),
      sliver: SliverToBoxAdapter(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final crossAxisCount = constraints.maxWidth > 600 ? 3 : 2;

            // Group sectors into rows
            final rows = <List<dynamic>>[];
            for (int i = 0; i < sectorsWithCounts.length; i += crossAxisCount) {
              rows.add(sectorsWithCounts.sublist(
                i,
                i + crossAxisCount > sectorsWithCounts.length
                    ? sectorsWithCounts.length
                    : i + crossAxisCount,
              ));
            }

            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: rows.map((row) {
                return Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child: IntrinsicHeight(
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: row.asMap().entries.map((entry) {
                        final index = entry.key;
                        final sector = entry.value;
                        final count =
                            provider.getSectorIndicatorCount(sector.name);

                        return Expanded(
                          child: Padding(
                            padding: EdgeInsets.only(
                              right: index < row.length - 1 ? 16 : 0,
                            ),
                            child: Card(
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(
                                    AppConstants.radiusLarge),
                              ),
                              shadowColor: Theme.of(context).ambientShadow(
                                  lightOpacity: 0.05, darkOpacity: 0.3),
                              child: InkWell(
                                onTap: () {
                                  provider.setSelectedSector(sector.name);
                                  provider.setViewMode('table');
                                  provider.applyFilters();
                                },
                                borderRadius: BorderRadius.circular(
                                    AppConstants.radiusLarge),
                                child: Padding(
                                  padding: const EdgeInsets.all(10),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.center,
                                    children: [
                                      const SizedBox(height: 4),
                                      if (sector.logoUrl != null)
                                        Image.network(
                                          sector.logoUrl!,
                                          width: 48,
                                          height: 48,
                                          fit: BoxFit.contain,
                                          errorBuilder:
                                              (context, error, stackTrace) {
                                            return Text(
                                              _getSectorIcon(sector.name),
                                              style:
                                                  const TextStyle(fontSize: 36),
                                            );
                                          },
                                        )
                                      else
                                        Text(
                                          _getSectorIcon(sector.name),
                                          style: const TextStyle(fontSize: 36),
                                        ),
                                      const SizedBox(height: 8),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(
                                            horizontal: 4),
                                        child: Text(
                                          sector.displayName,
                                          textAlign: TextAlign.center,
                                          style: TextStyle(
                                            fontSize: 15,
                                            fontWeight: FontWeight.bold,
                                            color: context.navyTextColor,
                                            height: 1.2,
                                          ),
                                        ),
                                      ),
                                      const SizedBox(height: 6),
                                      Text(
                                        '$count ${count == 1 ? localizations.indicatorBankIndicator : localizations.indicatorBankIndicators}',
                                        style: const TextStyle(
                                          fontSize: 11,
                                          color:
                                              Color(AppConstants.textSecondary),
                                        ),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        textAlign: TextAlign.center,
                                      ),
                                      if (sector.subsectors.isNotEmpty) ...[
                                        const SizedBox(height: 2),
                                        Builder(
                                          builder: (context) => GestureDetector(
                                            onTap: () async {
                                              final RenderBox? renderBox =
                                                  context.findRenderObject()
                                                      as RenderBox?;
                                              final position = renderBox
                                                  ?.localToGlobal(Offset.zero);
                                              final size = renderBox?.size;

                                              if (position != null &&
                                                  size != null) {
                                                final result =
                                                    await showMenu<String>(
                                                  context: context,
                                                  position:
                                                      RelativeRect.fromLTRB(
                                                    position.dx,
                                                    position.dy + size.height,
                                                    position.dx + size.width,
                                                    position.dy +
                                                        size.height +
                                                        200,
                                                  ),
                                                  items: [
                                                    PopupMenuItem<String>(
                                                      enabled: false,
                                                      child: Padding(
                                                        padding:
                                                            const EdgeInsets
                                                                .only(
                                                                bottom: 8),
                                                        child: Text(
                                                          'Sub-sectors',
                                                          style: TextStyle(
                                                            fontWeight:
                                                                FontWeight.bold,
                                                            fontSize: 14,
                                                            color: context
                                                                .navyTextColor,
                                                          ),
                                                        ),
                                                      ),
                                                    ),
                                                    const PopupMenuDivider(),
                                                    ...sector.subsectors
                                                        .map((subsector) {
                                                      // Count using English subsector name, not localized
                                                      final subCount = provider
                                                          .allIndicators
                                                          .where((ind) {
                                                        if (ind.subSector ==
                                                            null) {
                                                          return false;
                                                        }
                                                        if (ind.subSector
                                                            is String) {
                                                          return (ind.subSector
                                                                  as String) ==
                                                              subsector.name;
                                                        }
                                                        if (ind.subSector
                                                            is Map) {
                                                          final subSectorMap =
                                                              ind.subSector
                                                                  as Map<String,
                                                                      dynamic>;
                                                          final primarySubSectorName =
                                                              subSectorMap[
                                                                      'primary']
                                                                  as String?;
                                                          return primarySubSectorName ==
                                                              subsector.name;
                                                        }
                                                        return false;
                                                      }).length;
                                                      return PopupMenuItem<
                                                          String>(
                                                        value: subsector.name,
                                                        child: Row(
                                                          mainAxisAlignment:
                                                              MainAxisAlignment
                                                                  .spaceBetween,
                                                          children: [
                                                            Flexible(
                                                              child: Text(
                                                                subsector
                                                                    .displayName,
                                                                style:
                                                                    const TextStyle(
                                                                        fontSize:
                                                                            13),
                                                                maxLines: 2,
                                                                overflow:
                                                                    TextOverflow
                                                                        .ellipsis,
                                                              ),
                                                            ),
                                                            const SizedBox(
                                                                width: 8),
                                                            Text(
                                                              '$subCount',
                                                              style:
                                                                  const TextStyle(
                                                                fontSize: 12,
                                                                color: Color(
                                                                    AppConstants
                                                                        .textSecondary),
                                                              ),
                                                            ),
                                                          ],
                                                        ),
                                                      );
                                                    }),
                                                  ],
                                                );

                                                if (result != null) {
                                                  provider.setSelectedSector(
                                                      sector.name);
                                                  provider.setSelectedSubSector(
                                                      result);
                                                  provider.setViewMode('table');
                                                  provider.applyFilters();
                                                }
                                              }
                                            },
                                            child: Container(
                                              padding: const EdgeInsets.all(4),
                                              child: Icon(
                                                Icons.expand_more,
                                                size: 20,
                                                color: context.navyIconColor,
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ),
                );
              }).toList(),
            );
          },
        ),
      ),
    );
  }

  /// Groups [indicators] by [Indicator.displaySector]; empty sector → key `""`.
  Map<String, List<Indicator>> _groupIndicatorsBySector(
      List<Indicator> indicators) {
    final map = <String, List<Indicator>>{};
    for (final ind in indicators) {
      final key = ind.displaySector.trim();
      map.putIfAbsent(key, () => []).add(ind);
    }
    for (final list in map.values) {
      list.sort(
        (a, b) => a.displayName.toLowerCase().compareTo(
              b.displayName.toLowerCase(),
            ),
      );
    }
    return map;
  }

  List<String> _sortedSectorKeys(Map<String, List<Indicator>> grouped) {
    final keys = grouped.keys.toList();
    keys.sort((a, b) {
      if (a.isEmpty) return 1;
      if (b.isEmpty) return -1;
      return a.toLowerCase().compareTo(b.toLowerCase());
    });
    return keys;
  }

  Widget _buildTableView(IndicatorBankProvider provider) {
    final indicators = provider.filteredIndicators;

    final localizations = AppLocalizations.of(context)!;

    if (indicators.isEmpty) {
      return SliverFillRemaining(
        hasScrollBody: false,
        child: Center(
          child: Text(
            localizations.indicatorBankNoIndicators,
            style: const TextStyle(
              fontSize: 16,
              color: Color(AppConstants.textSecondary),
            ),
          ),
        ),
      );
    }

    final grouped = _groupIndicatorsBySector(indicators);
    final sectorKeys = _sortedSectorKeys(grouped);
    var totalChildCount = 1; // summary row
    for (final key in sectorKeys) {
      totalChildCount += 1 + grouped[key]!.length;
    }

    return SliverPadding(
      padding: EdgeInsets.symmetric(
        horizontal: MediaQuery.of(context).size.width > 600 ? 32 : 20,
      ),
      sliver: SliverList(
        delegate: SliverChildBuilderDelegate(
          (context, index) {
            if (index == 0) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 16, top: 8),
                child: Text(
                  '${localizations.indicatorBankShowing} ${indicators.length} ${indicators.length == 1 ? localizations.indicatorBankIndicator : localizations.indicatorBankIndicators}',
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w500,
                    color: Color(AppConstants.textSecondary),
                  ),
                ),
              );
            }

            var cursor = index - 1;
            for (var s = 0; s < sectorKeys.length; s++) {
              final sectorKey = sectorKeys[s];
              final listInSector = grouped[sectorKey]!;

              if (cursor == 0) {
                final title = sectorKey.isEmpty
                    ? localizations.other
                    : sectorKey;
                final isFirstSector = s == 0;
                return Padding(
                  padding: EdgeInsets.only(
                    top: isFirstSector ? 0 : 20,
                    bottom: 8,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          title,
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                            color: context.navyTextColor,
                          ),
                        ),
                      ),
                      Text(
                        '${listInSector.length}',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: context.textSecondaryColor,
                        ),
                      ),
                    ],
                  ),
                );
              }
              cursor -= 1;

              if (cursor < listInSector.length) {
                final indicator = listInSector[cursor];
                final isLastInList = index == totalChildCount - 1;
                return Card(
                  margin: EdgeInsets.only(bottom: isLastInList ? 24 : 8),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius:
                        BorderRadius.circular(AppConstants.radiusLarge),
                    side: BorderSide(
                      color: context.borderColor,
                      width: 1,
                    ),
                  ),
                  child: InkWell(
                    onTap: () {
                      Navigator.of(context).pushNamed(
                        '/indicator-bank/${indicator.id}',
                      );
                    },
                    borderRadius:
                        BorderRadius.circular(AppConstants.radiusLarge),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: Text(
                              indicator.displayName,
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w600,
                                color: context.textColor,
                              ),
                            ),
                          ),
                          const Icon(
                            Icons.chevron_right,
                            color: Color(AppConstants.textSecondary),
                            size: 18,
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              }
              cursor -= listInSector.length;
            }

            return const SizedBox.shrink();
          },
          childCount: totalChildCount,
        ),
      ),
    );
  }

  void _showProposeIndicatorModal() {
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) => _buildProposeModal(),
    );
  }

  Widget _buildProposeModal() {
    final localizations = AppLocalizations.of(context)!;

    return StatefulBuilder(
      builder: (context, setModalState) {
        return Dialog(
          insetPadding: const EdgeInsets.all(16),
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.of(context).size.height * 0.9,
              maxWidth: 600,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // Header
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Color(AppConstants.ifrcNavy),
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(AppConstants.radiusLarge),
                      topRight: Radius.circular(AppConstants.radiusLarge),
                    ),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Flexible(
                        child: Text(
                          localizations.indicatorBankProposeTitle,
                          style: TextStyle(
                            color: Theme.of(context).colorScheme.onPrimary,
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      IconButton(
                        icon: Icon(
                          Icons.close,
                          color: Theme.of(context).colorScheme.onPrimary,
                        ),
                        onPressed: () {
                          Navigator.of(context).pop();
                          setState(() {
                            _resetProposeForm();
                          });
                        },
                      ),
                    ],
                  ),
                ),
                // Content
                Flexible(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: _submitSuccess
                        ? _buildSuccessView()
                        : _buildProposeForm(
                            onStateChange: () => setModalState(() {}),
                          ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildSuccessView() {
    final localizations = AppLocalizations.of(context)!;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(
          Icons.check_circle,
          color: Color(AppConstants.successColor),
          size: 64,
        ),
        const SizedBox(height: 16),
        Text(
          localizations.indicatorBankProposeThankYou,
          style: const TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.bold,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          localizations.indicatorBankProposeSuccess,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 24),
        ElevatedButton(
          onPressed: () {
            Navigator.of(context).pop();
            setState(() {
              _resetProposeForm();
            });
          },
          style: ElevatedButton.styleFrom(
            backgroundColor: Color(AppConstants.ifrcRed),
            foregroundColor: Theme.of(context).colorScheme.onPrimary,
          ),
          child: Text(localizations.close),
        ),
      ],
    );
  }

  Widget _buildProposeForm({Function()? onStateChange}) {
    final localizations = AppLocalizations.of(context)!;

    return Form(
      key: _proposeFormKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Contact Information
          Text(
            localizations.indicatorBankProposeContactInfo,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _nameController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeYourName,
              border: const OutlineInputBorder(),
            ),
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankNameRequired
                : null,
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _emailController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeEmail,
              border: const OutlineInputBorder(),
            ),
            keyboardType: TextInputType.emailAddress,
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankEmailRequired
                : null,
          ),
          const SizedBox(height: 24),
          // Indicator Information
          Text(
            localizations.indicatorBankProposeIndicatorInfo,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _indicatorNameController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeIndicatorName,
              border: const OutlineInputBorder(),
            ),
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankIndicatorNameRequired
                : null,
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _definitionController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeDefinition,
              border: const OutlineInputBorder(),
            ),
            maxLines: 4,
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankDefinitionRequired
                : null,
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              Expanded(
                child: TextFormField(
                  controller: _typeController,
                  decoration: InputDecoration(
                    labelText: localizations.indicatorBankProposeType,
                    border: const OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: TextFormField(
                  controller: _unitController,
                  decoration: InputDecoration(
                    labelText: localizations.indicatorBankProposeUnit,
                    border: const OutlineInputBorder(),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),
          // Sector
          Text(
            localizations.indicatorBankProposeSector,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _sectorPrimaryController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposePrimarySector,
              border: const OutlineInputBorder(),
            ),
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankPrimarySectorRequired
                : null,
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _sectorSecondaryController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeSecondarySector,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _sectorTertiaryController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeTertiarySector,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          // Sub-Sector
          Text(
            localizations.indicatorBankProposeSubsector,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _subSectorPrimaryController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposePrimarySubsector,
              border: const OutlineInputBorder(),
            ),
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankPrimarySubsectorRequired
                : null,
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _subSectorSecondaryController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeSecondarySubsector,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          TextFormField(
            controller: _subSectorTertiaryController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeTertiarySubsector,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          // Emergency Context
          AppCheckboxListTile(
            title: localizations.indicatorBankProposeEmergency,
            value: _emergencyContext,
            onChanged: (value) {
              setState(() {
                _emergencyContext = value ?? false;
              });
            },
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _relatedProgramsController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeRelatedPrograms,
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _reasonController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeReason,
              border: const OutlineInputBorder(),
            ),
            maxLines: 3,
            validator: (value) => value?.isEmpty ?? true
                ? localizations.indicatorBankReasonRequired
                : null,
          ),
          const SizedBox(height: 16),
          TextFormField(
            controller: _additionalNotesController,
            decoration: InputDecoration(
              labelText: localizations.indicatorBankProposeAdditionalNotes,
              border: const OutlineInputBorder(),
            ),
            maxLines: 3,
          ),
          const SizedBox(height: 24),
          // Submit button
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _submittingProposal
                  ? null
                  : () => _submitProposal(onStateChange: onStateChange),
              style: ElevatedButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
                foregroundColor: Theme.of(context).colorScheme.onPrimary,
                padding: const EdgeInsets.symmetric(vertical: 16),
              ),
              child: _submittingProposal
                  ? SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          Theme.of(context).colorScheme.onPrimary,
                        ),
                      ),
                    )
                  : Text(localizations.indicatorBankProposeSubmit),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _submitProposal({Function()? onStateChange}) async {
    final localizations = AppLocalizations.of(context)!;

    if (!_proposeFormKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _submittingProposal = true;
    });
    onStateChange?.call();

    final provider = Provider.of<IndicatorBankProvider>(context, listen: false);
    final success = await provider.proposeNewIndicator({
      'submitter_name': _nameController.text,
      'submitter_email': _emailController.text,
      'suggestion_type': 'new_indicator',
      'indicator_id': null,
      'indicator_name': _indicatorNameController.text,
      'definition': _definitionController.text,
      'type': _typeController.text,
      'unit': _unitController.text,
      'sector': {
        'primary': _sectorPrimaryController.text,
        'secondary': _sectorSecondaryController.text,
        'tertiary': _sectorTertiaryController.text,
      },
      'sub_sector': {
        'primary': _subSectorPrimaryController.text,
        'secondary': _subSectorSecondaryController.text,
        'tertiary': _subSectorTertiaryController.text,
      },
      'emergency': _emergencyContext,
      'related_programs': _relatedProgramsController.text,
      'reason': _reasonController.text,
      'additional_notes': _additionalNotesController.text,
    });

    if (mounted) {
      setState(() {
        _submittingProposal = false;
        if (success) {
          _submitSuccess = true;
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.indicatorBankProposeFailed),
              backgroundColor: const Color(AppConstants.errorColor),
            ),
          );
        }
      });
      onStateChange?.call();
    }
  }

  void _resetProposeForm() {
    _nameController.clear();
    _emailController.clear();
    _indicatorNameController.clear();
    _definitionController.clear();
    _typeController.clear();
    _unitController.clear();
    _sectorPrimaryController.clear();
    _sectorSecondaryController.clear();
    _sectorTertiaryController.clear();
    _subSectorPrimaryController.clear();
    _subSectorSecondaryController.clear();
    _subSectorTertiaryController.clear();
    _relatedProgramsController.clear();
    _reasonController.clear();
    _additionalNotesController.clear();
    _emergencyContext = false;
    _submitSuccess = false;
    _proposeFormKey.currentState?.reset();
  }
}
