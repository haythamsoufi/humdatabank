import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../models/indicator_bank/indicator.dart';
import '../../models/indicator_bank/sector.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_navigation_drawer.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/ios_button.dart';
import '../../config/routes.dart';
import '../../utils/navigation_helper.dart';
import '../../l10n/app_localizations.dart';

// Top-level row model for list view (sector filter tiers). Must be library scope so
// types resolve in [_IndicatorBankScreenState].

abstract class _IbTableRow {
  const _IbTableRow();
}

class _IbRowSummary extends _IbTableRow {
  const _IbRowSummary() : super();
}

class _IbRowTierLabel extends _IbTableRow {
  const _IbRowTierLabel(this.title, {required this.marginTop}) : super();
  final String title;
  final double marginTop;
}

class _IbRowSectorHeader extends _IbTableRow {
  const _IbRowSectorHeader({
    required this.displayTitle,
    required this.count,
    required this.marginTop,
  }) : super();
  final String displayTitle;
  final int count;
  final double marginTop;
}

class _IbRowIndicator extends _IbTableRow {
  const _IbRowIndicator({required this.indicator, required this.isLastInList})
    : super();
  final Indicator indicator;
  final bool isLastInList;
}

class _IbSlotNames {
  const _IbSlotNames({this.primary, this.secondary, this.tertiary});
  final String? primary;
  final String? secondary;
  final String? tertiary;
}

_IbSlotNames _ibSectorSlots(Indicator ind) {
  if (ind.sector == null) return const _IbSlotNames();
  if (ind.sector is String) {
    return _IbSlotNames(primary: ind.sector as String);
  }
  if (ind.sector is Map) {
    final m = ind.sector as Map<String, dynamic>;
    return _IbSlotNames(
      primary: m['primary'] as String?,
      secondary: m['secondary'] as String?,
      tertiary: m['tertiary'] as String?,
    );
  }
  return const _IbSlotNames();
}

_IbSlotNames _ibSubSectorSlots(Indicator ind) {
  if (ind.subSector == null) return const _IbSlotNames();
  if (ind.subSector is String) {
    return _IbSlotNames(primary: ind.subSector as String);
  }
  if (ind.subSector is Map) {
    final m = ind.subSector as Map<String, dynamic>;
    return _IbSlotNames(
      primary: m['primary'] as String?,
      secondary: m['secondary'] as String?,
      tertiary: m['tertiary'] as String?,
    );
  }
  return const _IbSlotNames();
}

bool _ibPrimaryTierForFilters(Indicator ind, String selSector, String selSub) {
  final hasS = selSector.isNotEmpty;
  final hasU = selSub.isNotEmpty;
  if (!hasS && !hasU) return true;

  final sec = _ibSectorSlots(ind);
  final sub = _ibSubSectorSlots(ind);

  if (hasS && !hasU) {
    return sec.primary != null && sec.primary == selSector;
  }
  if (!hasS && hasU) {
    return sub.primary != null && sub.primary == selSub;
  }
  return sec.primary == selSector && sub.primary == selSub;
}

class IndicatorBankScreen extends StatefulWidget {
  const IndicatorBankScreen({super.key});

  @override
  State<IndicatorBankScreen> createState() => _IndicatorBankScreenState();
}

class _IndicatorBankScreenState extends State<IndicatorBankScreen> {
  final TextEditingController _searchController = TextEditingController();
  String? _lastLanguage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
    });
    _searchController.addListener(_onSearchChanged);
  }

  void _loadData({bool forceRefresh = false}) {
    final indicatorProvider = Provider.of<IndicatorBankProvider>(
      context,
      listen: false,
    );
    final languageProvider = Provider.of<LanguageProvider>(
      context,
      listen: false,
    );
    indicatorProvider.loadData(
      locale: languageProvider.currentLanguage,
      forceRefresh: forceRefresh,
    );
  }

  @override
  void dispose() {
    _searchController.dispose();
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
    final sheetHeight = MediaQuery.sizeOf(context).height * 0.9;
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return SizedBox(
          height: sheetHeight,
          child: Container(
            decoration: BoxDecoration(
              color: theme.scaffoldBackgroundColor,
              borderRadius: const BorderRadius.vertical(
                top: Radius.circular(20),
              ),
            ),
            child: SafeArea(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
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
                  const Expanded(child: CountriesWidget()),
                ],
              ),
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
              if (indicatorProvider.viewMode == 'table')
                IOSIconButton(
                  icon: Icons.filter_list,
                  onPressed: () => _openIndicatorBankFilters(indicatorProvider),
                  tooltip: localizations.indicatorBankShowFilters,
                  semanticLabel: localizations.indicatorBankShowFilters,
                ),
              IconButton(
                icon: const Icon(Icons.add),
                color: Color(AppConstants.ifrcRed),
                tooltip: localizations.indicatorBankProposeNew,
                onPressed: () {
                  Navigator.of(context).pushNamed(AppRoutes.proposeIndicator);
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
                  if (provider.isLoading && provider.allIndicators.isEmpty) {
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
                            style: IOSTextStyle.subheadline(
                              context,
                            ).copyWith(color: context.textSecondaryColor),
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
                                foregroundColor: Color(AppConstants.ifrcRed),
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
                      context,
                      index,
                    );
                  },
                )
              : null,
        );
      },
    );
  }

  Widget _buildSearchAndControls(IndicatorBankProvider provider) {
    final localizations = AppLocalizations.of(context)!;

    return Column(
      children: [
        // Search bar
        TextField(
          controller: _searchController,
          decoration: InputDecoration(
            hintText: localizations.indicatorBankSearchPlaceholder,
            prefixIcon: const Icon(
              Icons.search,
              color: Color(AppConstants.textSecondary),
            ),
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
        _buildViewModeToggle(provider),
      ],
    );
  }

  /// iOS-style sliding pill (single track + thumb) instead of M3 [SegmentedButton].
  Widget _buildViewModeToggle(IndicatorBankProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final isDark = context.isDarkTheme;
    final brandRed = Color(AppConstants.ifrcRed);

    return LayoutBuilder(
      builder: (context, constraints) {
        final maxW = constraints.maxWidth;
        final compact = maxW < 360;
        const outerPad = 4.0;
        final segmentW = (maxW - outerPad * 2) / 2;
        final isGrid = provider.viewMode == 'grid';

        final trackColor = isDark
            ? theme.colorScheme.surfaceContainerLow
            : const Color(0xFFE8E8ED);

        final thumbColor = isDark
            ? theme.colorScheme.surfaceContainerHigh
            : theme.colorScheme.surface;

        return SizedBox(
          height: 46,
          child: Container(
            padding: const EdgeInsets.all(outerPad),
            decoration: BoxDecoration(
              color: trackColor,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Stack(
              clipBehavior: Clip.hardEdge,
              children: [
                AnimatedPositioned(
                  duration: const Duration(milliseconds: 240),
                  curve: Curves.easeOutCubic,
                  left: isGrid ? 0 : segmentW,
                  top: 0,
                  width: segmentW,
                  height: 38,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: thumbColor,
                      borderRadius: BorderRadius.circular(10),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(
                            alpha: isDark ? 0.35 : 0.1,
                          ),
                          blurRadius: 6,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                  ),
                ),
                Row(
                  children: [
                    Expanded(
                      child: Semantics(
                        button: true,
                        selected: isGrid,
                        label: localizations.indicatorBankGridView,
                        child: Material(
                          color: Colors.transparent,
                          child: InkWell(
                            onTap: () {
                              if (provider.viewMode != 'grid') {
                                HapticFeedback.selectionClick();
                                provider.setViewMode('grid');
                              }
                            },
                            borderRadius: BorderRadius.circular(10),
                            child: _viewModeToggleSegmentContent(
                              compact: compact,
                              selected: isGrid,
                              icon: Icons.grid_view_rounded,
                              label: localizations.indicatorBankGridView,
                              brandRed: brandRed,
                            ),
                          ),
                        ),
                      ),
                    ),
                    Expanded(
                      child: Semantics(
                        button: true,
                        selected: !isGrid,
                        label: localizations.indicatorBankTableView,
                        child: Material(
                          color: Colors.transparent,
                          child: InkWell(
                            onTap: () {
                              if (provider.viewMode != 'table') {
                                HapticFeedback.selectionClick();
                                provider.setViewMode('table');
                              }
                            },
                            borderRadius: BorderRadius.circular(10),
                            child: _viewModeToggleSegmentContent(
                              compact: compact,
                              selected: !isGrid,
                              icon: Icons.view_list_rounded,
                              label: localizations.indicatorBankTableView,
                              brandRed: brandRed,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _viewModeToggleSegmentContent({
    required bool compact,
    required bool selected,
    required IconData icon,
    required String label,
    required Color brandRed,
  }) {
    final theme = Theme.of(context);
    final color = selected ? brandRed : theme.colorScheme.onSurfaceVariant;
    final weight = selected ? FontWeight.w600 : FontWeight.w500;

    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 8),
        child: compact
            ? Icon(icon, size: 22, color: color)
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, size: 20, color: color),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.labelLarge?.copyWith(
                        color: color,
                        fontWeight: weight,
                        letterSpacing: -0.2,
                      ),
                    ),
                  ),
                ],
              ),
      ),
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
                    key: ValueKey<String>(
                      'ib_sector_${provider.selectedSector}',
                    ),
                    initialValue: provider.selectedSector.isEmpty
                        ? null
                        : (sectorList.any(
                                (s) => s.name == provider.selectedSector,
                              )
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
                                (s) => s.name == provider.selectedSubSector,
                              )
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
                key: ValueKey<String>('ib_arch_${provider.archived}'),
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
              rows.add(
                sectorsWithCounts.sublist(
                  i,
                  i + crossAxisCount > sectorsWithCounts.length
                      ? sectorsWithCounts.length
                      : i + crossAxisCount,
                ),
              );
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
                        final count = provider.getSectorIndicatorCount(
                          sector.name,
                        );

                        return Expanded(
                          child: Padding(
                            padding: EdgeInsets.only(
                              right: index < row.length - 1 ? 16 : 0,
                            ),
                            child: Card(
                              elevation: 0,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(
                                  AppConstants.radiusLarge,
                                ),
                              ),
                              shadowColor: Theme.of(context).ambientShadow(
                                lightOpacity: 0.05,
                                darkOpacity: 0.3,
                              ),
                              child: InkWell(
                                onTap: () {
                                  provider.setSelectedSector(sector.name);
                                  provider.setViewMode('table');
                                  provider.applyFilters();
                                },
                                borderRadius: BorderRadius.circular(
                                  AppConstants.radiusLarge,
                                ),
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
                                                  style: const TextStyle(
                                                    fontSize: 36,
                                                  ),
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
                                          horizontal: 4,
                                        ),
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
                                          color: Color(
                                            AppConstants.textSecondary,
                                          ),
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
                                                final result = await showMenu<String>(
                                                  context: context,
                                                  position:
                                                      RelativeRect.fromLTRB(
                                                        position.dx,
                                                        position.dy +
                                                            size.height,
                                                        position.dx +
                                                            size.width,
                                                        position.dy +
                                                            size.height +
                                                            200,
                                                      ),
                                                  items: [
                                                    PopupMenuItem<String>(
                                                      enabled: false,
                                                      child: Padding(
                                                        padding:
                                                            const EdgeInsets.only(
                                                              bottom: 8,
                                                            ),
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
                                                    ...sector.subsectors.map((
                                                      subsector,
                                                    ) {
                                                      // Count using English subsector name, not localized
                                                      final subCount = provider.allIndicators.where((
                                                        ind,
                                                      ) {
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
                                                                  as Map<
                                                                    String,
                                                                    dynamic
                                                                  >;
                                                          final primarySubSectorName =
                                                              subSectorMap['primary']
                                                                  as String?;
                                                          return primarySubSectorName ==
                                                              subsector.name;
                                                        }
                                                        return false;
                                                      }).length;
                                                      return PopupMenuItem<
                                                        String
                                                      >(
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
                                                                          13,
                                                                    ),
                                                                maxLines: 2,
                                                                overflow:
                                                                    TextOverflow
                                                                        .ellipsis,
                                                              ),
                                                            ),
                                                            const SizedBox(
                                                              width: 8,
                                                            ),
                                                            Text(
                                                              '$subCount',
                                                              style: const TextStyle(
                                                                fontSize: 12,
                                                                color: Color(
                                                                  AppConstants
                                                                      .textSecondary,
                                                                ),
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
                                                    sector.name,
                                                  );
                                                  provider.setSelectedSubSector(
                                                    result,
                                                  );
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
    List<Indicator> indicators,
  ) {
    final map = <String, List<Indicator>>{};
    for (final ind in indicators) {
      final key = ind.displaySector.trim();
      map.putIfAbsent(key, () => []).add(ind);
    }
    for (final list in map.values) {
      list.sort(
        (a, b) =>
            a.displayName.toLowerCase().compareTo(b.displayName.toLowerCase()),
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

  List<_IbTableRow> _markLastIbIndicator(List<_IbTableRow> rows) {
    var last = -1;
    for (var i = rows.length - 1; i >= 0; i--) {
      if (rows[i] is _IbRowIndicator) {
        last = i;
        break;
      }
    }
    if (last < 0) return rows;
    final out = List<_IbTableRow>.from(rows);
    final old = out[last] as _IbRowIndicator;
    out[last] = _IbRowIndicator(indicator: old.indicator, isLastInList: true);
    return out;
  }

  void _appendIbRowsForGrouped(
    List<_IbTableRow> rows,
    Map<String, List<Indicator>> grouped,
    List<String> sectorKeys,
    AppLocalizations loc,
  ) {
    for (var s = 0; s < sectorKeys.length; s++) {
      final key = sectorKeys[s];
      final listInSector = grouped[key]!;
      final title = key.isEmpty ? loc.other : key;
      rows.add(
        _IbRowSectorHeader(
          displayTitle: title,
          count: listInSector.length,
          marginTop: s == 0 ? 0 : 20,
        ),
      );
      for (final ind in listInSector) {
        rows.add(_IbRowIndicator(indicator: ind, isLastInList: false));
      }
    }
  }

  /// When sector/sub-sector filters are on, primary-tier rows first; secondary/tertiary
  /// matches follow under **Also related**, still grouped by display (primary) sector.
  List<_IbTableRow> _buildIbTableRowsForList(
    IndicatorBankProvider provider,
    List<Indicator> indicators,
    AppLocalizations loc,
  ) {
    final rows = <_IbTableRow>[const _IbRowSummary()];
    final selS = provider.selectedSector;
    final selU = provider.selectedSubSector;
    final tiered = selS.isNotEmpty || selU.isNotEmpty;

    if (!tiered) {
      final grouped = _groupIndicatorsBySector(indicators);
      final keys = _sortedSectorKeys(grouped);
      _appendIbRowsForGrouped(rows, grouped, keys, loc);
      return _markLastIbIndicator(rows);
    }

    final primaryTier = <Indicator>[];
    final relatedTier = <Indicator>[];
    for (final ind in indicators) {
      if (_ibPrimaryTierForFilters(ind, selS, selU)) {
        primaryTier.add(ind);
      } else {
        relatedTier.add(ind);
      }
    }

    if (primaryTier.isNotEmpty) {
      final g = _groupIndicatorsBySector(primaryTier);
      final k = _sortedSectorKeys(g);
      _appendIbRowsForGrouped(rows, g, k, loc);
    }

    if (relatedTier.isNotEmpty) {
      rows.add(
        _IbRowTierLabel(
          loc.indicatorBankListTierAlsoRelated,
          marginTop: primaryTier.isNotEmpty ? 24 : 8,
        ),
      );
      final g = _groupIndicatorsBySector(relatedTier);
      final k = _sortedSectorKeys(g);
      _appendIbRowsForGrouped(rows, g, k, loc);
    }

    return _markLastIbIndicator(rows);
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

    final tableRows = _buildIbTableRowsForList(
      provider,
      indicators,
      localizations,
    );

    return SliverPadding(
      padding: EdgeInsets.symmetric(
        horizontal: MediaQuery.of(context).size.width > 600 ? 32 : 20,
      ),
      sliver: SliverList(
        delegate: SliverChildBuilderDelegate((context, index) {
          final row = tableRows[index];
          if (row is _IbRowSummary) {
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
          if (row is _IbRowTierLabel) {
            final theme = Theme.of(context);
            final bannerFill = Color(
              AppConstants.ifrcNavy,
            ).withValues(alpha: context.isDarkTheme ? 0.42 : 0.08);
            return Padding(
              padding: EdgeInsets.only(top: row.marginTop, bottom: 10),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: bannerFill,
                  border: Border(
                    left: BorderSide(
                      color: Color(AppConstants.ifrcRed),
                      width: 4,
                    ),
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Icon(
                        Icons.hub_outlined,
                        size: 22,
                        color: Color(AppConstants.ifrcRed),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          row.title,
                          style:
                              theme.textTheme.titleSmall?.copyWith(
                                fontWeight: FontWeight.w800,
                                height: 1.3,
                                letterSpacing: -0.15,
                                color: context.navyTextColor,
                              ) ??
                              TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w800,
                                height: 1.3,
                                color: context.navyTextColor,
                              ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }
          if (row is _IbRowSectorHeader) {
            return Padding(
              padding: EdgeInsets.only(top: row.marginTop, bottom: 8),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      row.displayTitle,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                        color: context.navyTextColor,
                      ),
                    ),
                  ),
                  Text(
                    '${row.count}',
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
          if (row is _IbRowIndicator) {
            final indicator = row.indicator;
            return Card(
              margin: EdgeInsets.only(bottom: row.isLastInList ? 24 : 8),
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
                side: BorderSide(color: context.borderColor, width: 1),
              ),
              child: InkWell(
                onTap: () {
                  Navigator.of(
                    context,
                  ).pushNamed('/indicator-bank/${indicator.id}');
                },
                borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
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
          return const SizedBox.shrink();
        }, childCount: tableRows.length),
      ),
    );
  }
}
