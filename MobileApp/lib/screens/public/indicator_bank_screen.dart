import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/indicator_bank/indicator.dart';
import '../../models/indicator_bank/sector.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/ios_button.dart';
import '../../config/routes.dart';
import '../../config/app_config.dart';
import '../../utils/url_helper.dart';
import '../../services/webview_service.dart';
import '../../l10n/app_localizations.dart';

class IndicatorBankScreen extends StatefulWidget {
  const IndicatorBankScreen({super.key});

  @override
  State<IndicatorBankScreen> createState() => _IndicatorBankScreenState();
}

class _IndicatorBankScreenState extends State<IndicatorBankScreen> {
  final TextEditingController _searchController = TextEditingController();
  bool _showFilters = false;
  bool _showProposeModal = false;
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
      setState(() {
        _showFilters = false;
      });
    }
  }

  Widget _buildNavigationDrawer(BuildContext context, LanguageProvider languageProvider, ThemeData theme, AppLocalizations localizations) {
    final language = languageProvider.currentLanguage;
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final user = authProvider.user;
    final isAdmin = user != null && (user.role == 'admin' || user.role == 'system_manager');
    final isAuthenticated = authProvider.isAuthenticated;
    final isFocalPoint = user != null && user.role == 'focal_point';
    final isDark = theme.brightness == Brightness.dark;

    return Drawer(
      backgroundColor: isDark
          ? IOSColors.secondarySystemBackgroundDark
          : IOSColors.systemBackground,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.zero,
      ),
      child: SafeArea(
        child: Column(
          children: [
            // Title
            Padding(
              padding: const EdgeInsets.fromLTRB(
                IOSSpacing.xl,
                IOSSpacing.lg,
                IOSSpacing.xl,
                IOSSpacing.md,
              ),
              child: Text(
                localizations.navigation,
                style: IOSTextStyle.title2(context),
              ),
            ),
            // Scrollable menu items
            Expanded(
              child: ListView(
                padding: EdgeInsets.zero,
                children: [
                  // Menu items
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.home,
                    title: localizations.home ?? 'Global Overview',
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).popUntil((route) {
                        return route.isFirst ||
                            route.settings.name == AppRoutes.dashboard;
                      });
                    },
                  ),
                  // Indicator Bank - already here, just pop drawer
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.library_books,
                    title: localizations.indicatorBank,
                    onTap: () {
                      Navigator.pop(context);
                      // Already on Indicator Bank screen
                    },
                  ),
                  // Quiz Game - navigate to quiz game screen
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.quiz,
                    title: localizations.quizGame,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pushNamed(
                        AppRoutes.quizGame,
                      );
                    },
                  ),
                  // AI Assistant (ChatGPT-like native chat)
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.smart_toy_outlined,
                    title: 'AI Assistant',
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pushNamed(AppRoutes.aiChat);
                    },
                  ),
                  // Resources/Notifications - navigate to native screen
                  if (isFocalPoint)
                    _buildMenuTile(
                      context: context,
                      theme: theme,
                      icon: Icons.notifications,
                      title: localizations.notifications ?? 'Notifications',
                      onTap: () {
                        Navigator.pop(context);
                        Navigator.of(context).pop();
                        Navigator.of(context).pushNamed(AppRoutes.notifications);
                      },
                    )
                  else
                    _buildMenuTile(
                      context: context,
                      theme: theme,
                      icon: Icons.folder,
                      title: localizations.resources ?? 'Resources',
                      onTap: () {
                        Navigator.pop(context);
                        Navigator.of(context).pop();
                        Navigator.of(context).pushNamed(AppRoutes.resources);
                      },
                    ),
                  // Countries - show in bottom sheet
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.public,
                    title: localizations.countries,
                    onTap: () {
                      Navigator.pop(context);
                      _showCountriesSheet(context, theme);
                    },
                  ),
                  // Analysis section header
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      IOSSpacing.xl,
                      IOSSpacing.lg,
                      IOSSpacing.xl,
                      IOSSpacing.sm,
                    ),
                    child: Text(
                      localizations.analysis.toUpperCase(),
                      style: IOSTextStyle.footnote(context).copyWith(
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  // Disaggregation Analysis - navigate to native screen
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.analytics,
                    title: localizations.disaggregationAnalysis,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
                      Navigator.of(context).pushNamed(AppRoutes.disaggregationAnalysis);
                    },
                  ),
                  // Data Visualization - use webview (no native screen)
                  _buildMenuTile(
                    context: context,
                    theme: theme,
                    icon: Icons.bar_chart,
                    title: localizations.dataVisualization,
                    showDivider: false,
                    onTap: () {
                      Navigator.pop(context);
                      Navigator.of(context).pop();
                      final fullUrl = UrlHelper.buildFrontendUrlWithLanguage('/dataviz', language);
                      Navigator.of(context).pushNamed(
                        AppRoutes.webview,
                        arguments: fullUrl,
                      );
                    },
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
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
                        tooltip: localizations.close ?? 'Close',
                        semanticLabel: localizations.close ?? 'Close',
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1),
                // Countries widget
                Expanded(
                  child: const CountriesWidget(),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildMenuTile({
    required BuildContext context,
    required ThemeData theme,
    required IconData icon,
    required String title,
    required VoidCallback onTap,
    bool showDivider = true,
  }) {
    final isDark = theme.brightness == Brightness.dark;

    return Column(
      children: [
        InkWell(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: IOSSpacing.xl,
              vertical: IOSSpacing.md,
            ),
            child: Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: IOSColors.getSystemBlue(context).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Icon(
                    icon,
                    color: IOSColors.getSystemBlue(context),
                    size: 18,
                  ),
                ),
                const SizedBox(width: IOSSpacing.md),
                Expanded(
                  child: Text(
                    title,
                    style: IOSTextStyle.body(context),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (showDivider)
          Divider(
            height: 1,
            thickness: 0.5,
            indent: IOSSpacing.xl,
            endIndent: 0,
            color: theme.dividerColor.withOpacity(0.3),
          ),
      ],
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
        // Determine FAB location based on language direction
        // In RTL (Arabic), startFloat puts button on visual right
        // In LTR, endFloat puts button on visual right
        final isRTL = currentLanguage == 'ar';
        final fabLocation = isRTL
            ? FloatingActionButtonLocation.startFloat
            : FloatingActionButtonLocation.endFloat;

        return Scaffold(
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
          ),
          drawer: _buildNavigationDrawer(context, languageProvider, theme, localizations),
          body: Container(
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
                                // Filters
                                if (_showFilters &&
                                    provider.viewMode == 'table')
                                  _buildFilters(provider),
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
          floatingActionButton: LayoutBuilder(
            builder: (context, constraints) {
              if (constraints.maxWidth > 400) {
                final theme = Theme.of(context);
                return FloatingActionButton.extended(
                  heroTag: 'propose_button',
                  onPressed: () {
                    _resetProposeForm();
                    _showProposeIndicatorModal();
                  },
                  backgroundColor: Color(AppConstants.ifrcRed),
                  icon: Icon(Icons.add, color: theme.colorScheme.onPrimary),
                  label: Text(
                    localizations.indicatorBankProposeNew,
                    style: TextStyle(color: theme.colorScheme.onPrimary),
                  ),
                );
              } else {
                final theme = Theme.of(context);
                return FloatingActionButton(
                  heroTag: 'propose_button',
                  onPressed: () {
                    _resetProposeForm();
                    _showProposeIndicatorModal();
                  },
                  backgroundColor: Color(AppConstants.ifrcRed),
                  child: Icon(Icons.add, color: theme.colorScheme.onPrimary),
                  tooltip: localizations.indicatorBankProposeNew,
                );
              }
            },
          ),
          floatingActionButtonLocation: fabLocation,
          bottomNavigationBar: _isStandaloneScreen(context)
              ? AppBottomNavigationBar(
                  currentIndex: 2, // Home tab highlighted
                  onTap: (index) {
                    // Navigate back to main navigation screen
                    Navigator.of(context).popUntil((route) {
                      return route.isFirst ||
                          route.settings.name == AppRoutes.dashboard;
                    });
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
        // Controls row
        Row(
          children: [
            // View mode toggle - iOS style segmented control
            Container(
              decoration: BoxDecoration(
                color: Theme.of(context).brightness == Brightness.dark
                    ? Colors.grey[850]?.withOpacity(0.5)
                    : Colors.grey[200]?.withOpacity(0.6),
                borderRadius: BorderRadius.circular(10),
              ),
              padding: const EdgeInsets.all(3),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildViewModeButton(
                    provider,
                    'grid',
                    Icons.grid_view,
                    localizations.indicatorBankGridView,
                  ),
                  _buildViewModeButton(
                    provider,
                    'table',
                    Icons.table_rows,
                    localizations.indicatorBankTableView,
                  ),
                ],
              ),
            ),
            // Filter toggle (only show in table mode)
            if (provider.viewMode == 'table') ...[
              const SizedBox(width: 12),
              Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: () {
                    setState(() {
                      _showFilters = !_showFilters;
                    });
                  },
                  borderRadius: BorderRadius.circular(10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        vertical: 10, horizontal: 14),
                    decoration: BoxDecoration(
                      color: Theme.of(context).brightness == Brightness.dark
                          ? Colors.grey[800]?.withOpacity(0.6)
                          : Colors.white,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: Theme.of(context).brightness == Brightness.dark
                            ? Colors.grey[700]!.withOpacity(0.5)
                            : Colors.grey[300]!,
                        width: 0.5,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Theme.of(context).brightness == Brightness.dark
                              ? Colors.black.withOpacity(0.3)
                              : Colors.black.withOpacity(0.05),
                          blurRadius: 4,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _showFilters
                              ? Icons.filter_list_off
                              : Icons.filter_list,
                          size: 18,
                          color: Theme.of(context).brightness == Brightness.dark
                              ? Colors.white
                              : Colors.black87,
                        ),
                        const SizedBox(width: 6),
                        Text(
                          _showFilters
                              ? localizations.indicatorBankHideFilters
                              : localizations.indicatorBankShowFilters,
                          overflow: TextOverflow.ellipsis,
                          maxLines: 1,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                            color:
                                Theme.of(context).brightness == Brightness.dark
                                    ? Colors.white
                                    : Colors.black87,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }

  Widget _buildViewModeButton(
    IndicatorBankProvider provider,
    String mode,
    IconData icon,
    String tooltip,
  ) {
    final isSelected = provider.viewMode == mode;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeInOut,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: isSelected
            ? (isDark ? Colors.white.withOpacity(0.15) : Colors.white)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
        boxShadow: isSelected && !isDark
            ? [
                BoxShadow(
                  color: Colors.black.withOpacity(0.08),
                  blurRadius: 4,
                  offset: const Offset(0, 1),
                ),
              ]
            : null,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            provider.setViewMode(mode);
          },
          borderRadius: BorderRadius.circular(8),
          child: Icon(
            icon,
            color: isSelected
                ? (isDark ? Colors.white : Color(AppConstants.ifrcRed))
                : (isDark ? Colors.grey[400] : Colors.grey[600]),
            size: 20,
          ),
        ),
      ),
    );
  }

  Widget _buildFilters(IndicatorBankProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Container(
      margin: const EdgeInsets.only(top: 16),
      decoration: BoxDecoration(
        color: theme.cardColor,
        borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        border: Border.all(
          color: const Color(AppConstants.borderColor),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(
                  color: const Color(AppConstants.borderColor),
                  width: 0.5,
                ),
              ),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: context.navyBackgroundColor(opacity: 0.1),
                    borderRadius:
                        BorderRadius.circular(AppConstants.radiusMedium),
                  ),
                  child: Icon(
                    Icons.filter_list,
                    size: 18,
                    color: context.navyIconColor,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  localizations.indicatorBankFilters,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color:
                        theme.textTheme.titleLarge?.color ?? context.textColor,
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Type filter
                DropdownButtonFormField<String>(
                  value: provider.selectedType.isEmpty
                      ? null
                      : provider.selectedType,
                  decoration: InputDecoration(
                    labelText: localizations.indicatorBankFilterType,
                    border: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusLarge),
                      borderSide: const BorderSide(
                        color: Color(AppConstants.borderColor),
                      ),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusLarge),
                      borderSide: const BorderSide(
                        color: Color(AppConstants.borderColor),
                      ),
                    ),
                    filled: true,
                    fillColor: theme.colorScheme.surface,
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 16),
                  ),
                  isExpanded: true,
                  items: [
                    DropdownMenuItem<String>(
                      value: null,
                      child: Text(localizations.indicatorBankFilterTypeAll,
                          overflow: TextOverflow.ellipsis),
                    ),
                    ...provider.types.map((type) => DropdownMenuItem<String>(
                          value: type,
                          child: Text(type, overflow: TextOverflow.ellipsis),
                        )),
                  ],
                  onChanged: (value) {
                    provider.setSelectedType(value ?? '');
                  },
                ),
                const SizedBox(height: 16),
                // Sector filter
                Builder(
                  builder: (context) {
                    // Get unique sectors by name to avoid duplicates
                    final uniqueSectors = <String, Sector>{};
                    for (final sector in provider.sectors) {
                      if (!uniqueSectors.containsKey(sector.name)) {
                        uniqueSectors[sector.name] = sector;
                      }
                    }
                    final sectorList = uniqueSectors.values.toList();

                    return DropdownButtonFormField<String>(
                      value: provider.selectedSector.isEmpty
                          ? null
                          : (sectorList
                                  .any((s) => s.name == provider.selectedSector)
                              ? provider.selectedSector
                              : null),
                      decoration: InputDecoration(
                        labelText: localizations.indicatorBankFilterSector,
                        border: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                          borderSide: const BorderSide(
                            color: Color(AppConstants.borderColor),
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                          borderSide: const BorderSide(
                            color: Color(AppConstants.borderColor),
                          ),
                        ),
                        filled: true,
                        fillColor: theme.colorScheme.surface,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 16),
                      ),
                      isExpanded: true,
                      items: [
                        DropdownMenuItem<String>(
                          value: null,
                          child: Text(
                              localizations.indicatorBankFilterSectorAll,
                              overflow: TextOverflow.ellipsis),
                        ),
                        ...sectorList.map((sector) => DropdownMenuItem<String>(
                              value: sector.name,
                              child: Text(
                                sector.displayName,
                                overflow: TextOverflow.ellipsis,
                              ),
                            )),
                      ],
                      onChanged: (value) {
                        provider.setSelectedSector(value ?? '');
                      },
                    );
                  },
                ),
                const SizedBox(height: 16),
                // SubSector filter
                Builder(
                  builder: (context) {
                    // Get unique subsectors by name to avoid duplicates
                    final allSubsectors = provider.sectors
                        .expand((s) => s.subsectors)
                        .where((sub) =>
                            provider.selectedSector.isEmpty ||
                            sub.sectorId ==
                                provider.sectors
                                    .firstWhere(
                                      (s) => s.name == provider.selectedSector,
                                      orElse: () => provider.sectors.first,
                                    )
                                    .id)
                        .toList();

                    final uniqueSubsectors = <String, SubSector>{};
                    for (final subsector in allSubsectors) {
                      if (!uniqueSubsectors.containsKey(subsector.name)) {
                        uniqueSubsectors[subsector.name] = subsector;
                      }
                    }
                    final subsectorList = uniqueSubsectors.values.toList();

                    return DropdownButtonFormField<String>(
                      value: provider.selectedSubSector.isEmpty
                          ? null
                          : (subsectorList.any(
                                  (s) => s.name == provider.selectedSubSector)
                              ? provider.selectedSubSector
                              : null),
                      decoration: InputDecoration(
                        labelText: localizations.indicatorBankFilterSubsector,
                        border: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                          borderSide: const BorderSide(
                            color: Color(AppConstants.borderColor),
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius:
                              BorderRadius.circular(AppConstants.radiusLarge),
                          borderSide: const BorderSide(
                            color: Color(AppConstants.borderColor),
                          ),
                        ),
                        filled: true,
                        fillColor: theme.colorScheme.surface,
                        contentPadding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 16),
                      ),
                      isExpanded: true,
                      items: [
                        DropdownMenuItem<String>(
                          value: null,
                          child: Text(
                              localizations.indicatorBankFilterSubsectorAll,
                              overflow: TextOverflow.ellipsis),
                        ),
                        ...subsectorList
                            .map((subsector) => DropdownMenuItem<String>(
                                  value: subsector.name,
                                  child: Text(
                                    subsector.displayName,
                                    overflow: TextOverflow.ellipsis,
                                  ),
                                )),
                      ],
                      onChanged: (value) {
                        provider.setSelectedSubSector(value ?? '');
                      },
                    );
                  },
                ),
                const SizedBox(height: 16),
                // Archived filter
                DropdownButtonFormField<String>(
                  value: provider.archived ? 'all' : 'active',
                  decoration: InputDecoration(
                    labelText: localizations.indicatorBankFilterStatus,
                    border: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusLarge),
                      borderSide: const BorderSide(
                        color: Color(AppConstants.borderColor),
                      ),
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusLarge),
                      borderSide: const BorderSide(
                        color: Color(AppConstants.borderColor),
                      ),
                    ),
                    filled: true,
                    fillColor: theme.colorScheme.surface,
                    contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 16),
                  ),
                  isExpanded: true,
                  items: [
                    DropdownMenuItem<String>(
                      value: 'active',
                      child: Text(localizations.indicatorBankFilterStatusActive,
                          overflow: TextOverflow.ellipsis),
                    ),
                    DropdownMenuItem<String>(
                      value: 'all',
                      child: Text(localizations.indicatorBankFilterStatusAll,
                          overflow: TextOverflow.ellipsis),
                    ),
                  ],
                  onChanged: (value) {
                    provider.setArchived(value == 'all');
                  },
                ),
                const SizedBox(height: 20),
                // Action buttons
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () {
                          provider.applyFilters();
                        },
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Color(AppConstants.ifrcRed),
                          foregroundColor:
                              Theme.of(context).colorScheme.onPrimary,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppConstants.radiusLarge),
                          ),
                          elevation: 0,
                        ),
                        child: Text(
                          localizations.indicatorBankApplyFilters,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () {
                          provider.clearFilters();
                          _searchController.clear();
                          setState(() {
                            _showFilters = false;
                          });
                        },
                        style: OutlinedButton.styleFrom(
                          foregroundColor: context.navyForegroundColor,
                          side: BorderSide(
                            color: context.borderColor,
                          ),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(
                            borderRadius:
                                BorderRadius.circular(AppConstants.radiusLarge),
                          ),
                        ),
                        child: Text(
                          localizations.indicatorBankClearAll,
                          style: const TextStyle(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
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
            final cardWidth =
                (constraints.maxWidth - (crossAxisCount - 1) * 16) /
                    crossAxisCount;

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
                              shadowColor: Theme.of(context).brightness ==
                                      Brightness.dark
                                  ? Colors.black.withOpacity(0.3)
                                  : Colors.black.withOpacity(0.05),
                              child: InkWell(
                                onTap: () {
                                  provider.setSelectedSector(sector.name);
                                  provider.setViewMode('table');
                                  setState(() {
                                    _showFilters = false;
                                  });
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
                                                            null) return false;
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
                                                  setState(() {
                                                    _showFilters = false;
                                                  });
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

    return SliverPadding(
      padding: EdgeInsets.symmetric(
        horizontal: MediaQuery.of(context).size.width > 600 ? 32 : 20,
      ),
      sliver: SliverList(
        delegate: SliverChildBuilderDelegate(
          (context, index) {
            if (index == 0) {
              // Show count at the top
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

            final indicator = indicators[index - 1];
            final isLast = index == indicators.length;

            return Card(
              margin: EdgeInsets.only(bottom: isLast ? 100 : 8),
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
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
                borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Row(
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
                      if (indicator.displayType.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          '${localizations.indicatorBankTableType}: ${indicator.displayType}',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Color(AppConstants.textSecondary),
                          ),
                        ),
                      ],
                      if (indicator.displaySector.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          '${localizations.indicatorBankTableSector}: ${indicator.displaySector}',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Color(AppConstants.textSecondary),
                          ),
                        ),
                      ],
                      if (indicator.displaySubSector.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          '${localizations.indicatorBankTableSubsector}: ${indicator.displaySubSector}',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Color(AppConstants.textSecondary),
                          ),
                        ),
                      ],
                      if (indicator.displayUnit.isNotEmpty) ...[
                        const SizedBox(height: 3),
                        Text(
                          '${localizations.indicatorBankTableUnit}: ${indicator.displayUnit}',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Color(AppConstants.textSecondary),
                          ),
                        ),
                      ],
                      if (indicator.displayDefinition.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        Text(
                          indicator.displayDefinition,
                          style: const TextStyle(
                            fontSize: 12,
                            color: Color(AppConstants.textSecondary),
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            );
          },
          childCount: indicators.length + 1, // +1 for the count header
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
                    borderRadius: BorderRadius.only(
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
