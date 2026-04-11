import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/dashboard_provider.dart';
import '../../providers/shared/notification_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../widgets/assignment_card.dart';
import '../../widgets/app_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../models/shared/assignment.dart';
import '../../l10n/app_localizations.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/error_state.dart';
import '../../widgets/app_fade_in_up.dart';
import '../../widgets/entity_selector_bottom_sheet.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  // Filter state for past assignments
  String? _selectedPeriodFilter;
  String? _selectedTemplateFilter;
  String? _selectedStatusFilter;

  // Track previous language to detect changes
  String? _previousLanguage;

  // Track if we've completed at least one load to avoid showing empty state prematurely
  bool _hasLoadedOnce = false;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _fadeAnimation = CurvedAnimation(
      parent: _animationController,
      curve: IOSCurves.easeOut,
    );
    // Get initial language
    final languageProvider =
        Provider.of<LanguageProvider>(context, listen: false);
    _previousLanguage = languageProvider.currentLanguage;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
      _animationController.forward();
    });
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  Future<void> _loadData({bool forceRefresh = false}) async {
    final dashboardProvider =
        Provider.of<DashboardProvider>(context, listen: false);
    final notificationProvider =
        Provider.of<NotificationProvider>(context, listen: false);
    final authProvider = Provider.of<AuthProvider>(context, listen: false);

    // Force revalidation on dashboard load to ensure fresh session and role
    // This ensures we have a valid session before making API calls
    final isAuthenticated = await authProvider.checkAuthStatus(forceRevalidate: true);

    // Load dashboard regardless of auth status (non-authenticated users can still view)
    // Force refresh if authenticated or if explicitly requested (e.g., language change)
    await dashboardProvider.loadDashboard(forceRefresh: isAuthenticated || forceRefresh);

    // Mark that we've completed at least one load
    if (mounted) {
      setState(() {
        _hasLoadedOnce = true;
      });
    }

    // Refresh user after dashboard loads to get updated profile data including profile color
    if (isAuthenticated) {
      await authProvider.refreshUser();
      dashboardProvider.loadEntities();
      notificationProvider.refreshUnreadCount(authProvider: authProvider);
    }
  }

  bool _shouldShowEnterDataButton(String? userRole, Assignment assignment) {
    // Align with dashboard.html: no Enter Data when assignment form is effectively closed
    if (assignment.isEffectivelyClosed) {
      return false;
    }
    // For admins and system managers: always show
    if (userRole == 'admin' || userRole == 'system_manager') {
      return true;
    }

    // For focal points (assignment_editor_submitter): same statuses as Backoffice template
    if (userRole == 'focal_point') {
      final statusLower = assignment.status.toLowerCase();
      return statusLower != 'submitted' &&
          statusLower != 'approved' &&
          statusLower != 'requires revision';
    }

    // For other roles: don't show
    return false;
  }

  /// Past list order matches main.dashboard: due date ascending, nulls last (then id).
  List<Assignment> _sortedPastAssignments(List<Assignment> items) {
    final copy = List<Assignment>.from(items);
    copy.sort((a, b) {
      if (a.dueDate == null && b.dueDate == null) {
        return a.id.compareTo(b.id);
      }
      if (a.dueDate == null) return 1;
      if (b.dueDate == null) return -1;
      final byDue = a.dueDate!.compareTo(b.dueDate!);
      if (byDue != 0) return byDue;
      return a.id.compareTo(b.id);
    });
    return copy;
  }

  // Past section: filters + single list (same structure as dashboard.html table, not status sub-groups)
  Widget _buildPastAssignmentsSection(DashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    // Get unique values for filters
    final periods = provider.pastAssignments
        .map((a) => a.periodName)
        .whereType<String>()
        .where((p) => p.isNotEmpty)
        .toSet()
        .toList()
      ..sort();

    final templates = provider.pastAssignments
        .map((a) => a.templateName)
        .whereType<String>()
        .where((t) => t.isNotEmpty)
        .toSet()
        .toList()
      ..sort();

    final statuses =
        provider.pastAssignments.map((a) => a.status).toSet().toList()..sort();

    // Filter assignments
    final filteredAssignments = provider.pastAssignments.where((assignment) {
      if (_selectedPeriodFilter != null &&
          assignment.periodName != _selectedPeriodFilter) {
        return false;
      }
      if (_selectedTemplateFilter != null &&
          assignment.templateName != _selectedTemplateFilter) {
        return false;
      }
      if (_selectedStatusFilter != null &&
          assignment.status != _selectedStatusFilter) {
        return false;
      }
      return true;
    }).toList();

    final sortedPast = _sortedPastAssignments(filteredAssignments);

    final theme = Theme.of(context);
    return Container(
      margin: EdgeInsets.zero,
      child: Theme(
        data: theme.copyWith(
          dividerColor: Colors.transparent,
        ),
        child: ExpansionTile(
          tilePadding: const EdgeInsets.symmetric(
            horizontal: IOSSpacing.lg,
            vertical: IOSSpacing.xs,
          ),
          minTileHeight: 40,
          dense: true,
          initiallyExpanded: false,
          backgroundColor: Colors.transparent,
          collapsedBackgroundColor: Colors.transparent,
          shape: const Border(),
          collapsedShape: const Border(),
          title: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                localizations.pastAssignments.toUpperCase(),
                style: IOSTextStyle.footnote(context).copyWith(
                  fontWeight: FontWeight.w600,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  letterSpacing: 0.5,
                ),
              ),
              SizedBox(width: IOSSpacing.smOf(context)),
              Container(
              padding: EdgeInsets.symmetric(
                horizontal: IOSSpacing.xsOf(context) + 2,
                vertical: IOSSpacing.xsOf(context) / 2,
              ),
                decoration: BoxDecoration(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusSmallOf(context)),
                ),
                child: Text(
                  '${filteredAssignments.length}',
                  style: IOSTextStyle.caption2(context).copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          children: [
            // Filters Section - iOS style
            if (periods.isNotEmpty ||
                templates.isNotEmpty ||
                statuses.isNotEmpty)
              LayoutBuilder(
                builder: (context, constraints) {
                  final canFitInline = constraints.maxWidth > 400; // Approximate breakpoint
                  return Container(
                    padding: EdgeInsets.fromLTRB(
                      IOSSpacing.lgOf(context),
                      IOSSpacing.smOf(context),
                      IOSSpacing.lgOf(context),
                      IOSSpacing.mdOf(context),
                    ),
                    child: canFitInline
                        ? Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              Text(
                                localizations.filters.toUpperCase(),
                                style: IOSTextStyle.footnote(context).copyWith(
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.5,
                                ),
                              ),
                              SizedBox(width: IOSSpacing.mdOf(context)),
                              Expanded(
                                child: Wrap(
                                  spacing: IOSSpacing.sm,
                                  runSpacing: IOSSpacing.sm,
                                  children: _buildFilterButtons(localizations, theme, periods, templates, statuses),
                                ),
                              ),
                            ],
                          )
                        : Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                localizations.filters.toUpperCase(),
                                style: IOSTextStyle.footnote(context).copyWith(
                                  fontWeight: FontWeight.w600,
                                  letterSpacing: 0.5,
                                ),
                              ),
                              SizedBox(height: IOSSpacing.mdOf(context) - 4),
                              Wrap(
                                spacing: IOSSpacing.sm,
                                runSpacing: IOSSpacing.sm,
                                children: _buildFilterButtons(localizations, theme, periods, templates, statuses),
                              ),
                            ],
                          ),
                  );
                },
              ),

            // Single list (dashboard.html: one table for all past rows)
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 0, 0, IOSSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (sortedPast.isNotEmpty)
                    Padding(
                      padding: EdgeInsets.symmetric(horizontal: IOSSpacing.lgOf(context)),
                      child: Column(
                        children: sortedPast.asMap().entries.map((entry) {
                          final index = entry.key;
                          return _buildPastAssignmentCard(entry.value, index);
                        }).toList(),
                      ),
                    ),

                  // Empty filtered state
                  if (filteredAssignments.isEmpty)
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
                      padding: const EdgeInsets.all(IOSSpacing.xxl),
                      child: Column(
                        children: [
                          Icon(
                            Icons.filter_alt_off_rounded,
                            size: 48,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurface
                                .withValues(alpha: 0.4),
                          ),
                          SizedBox(height: IOSSpacing.mdOf(context)),
                          Text(
                            localizations.noAssignmentsMatchFilters,
                            style: IOSTextStyle.subheadline(context).copyWith(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withValues(alpha: 0.6),
                              fontWeight: FontWeight.w500,
                            ),
                            textAlign: TextAlign.center,
                          ),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildFilterButtons(
    AppLocalizations localizations,
    ThemeData theme,
    List<String> periods,
    List<String> templates,
    List<String> statuses,
  ) {
    return [
      // Period Filter
      if (periods.isNotEmpty)
        _buildIOSFilterButton(
          label: localizations.period,
          value: _selectedPeriodFilter,
          options: periods,
          onTap: () => _showIOSFilterPicker(
            context: context,
            title: localizations.period,
            options: periods,
            selectedValue: _selectedPeriodFilter,
            onSelected: (value) {
              HapticFeedback.selectionClick();
              setState(() {
                _selectedPeriodFilter = value;
              });
            },
            localizations: localizations,
          ),
          isStatusFilter: false,
        ),
      // Template Filter
      if (templates.isNotEmpty)
        _buildIOSFilterButton(
          label: localizations.template,
          value: _selectedTemplateFilter,
          options: templates,
          onTap: () => _showIOSFilterPicker(
            context: context,
            title: localizations.template,
            options: templates,
            selectedValue: _selectedTemplateFilter,
            onSelected: (value) {
              HapticFeedback.selectionClick();
              setState(() {
                _selectedTemplateFilter = value;
              });
            },
            localizations: localizations,
          ),
          isStatusFilter: false,
        ),
      // Status Filter
      if (statuses.isNotEmpty)
        _buildIOSFilterButton(
          label: localizations.status,
          value: _selectedStatusFilter,
          options: statuses,
          onTap: () => _showIOSFilterPicker(
            context: context,
            title: localizations.status,
            options: statuses,
            selectedValue: _selectedStatusFilter,
            onSelected: (value) {
              HapticFeedback.selectionClick();
              setState(() {
                _selectedStatusFilter = value;
              });
            },
            localizations: localizations,
            isStatusFilter: true,
          ),
          isStatusFilter: true,
        ),
      // Clear Filters
      if (_selectedPeriodFilter != null ||
          _selectedTemplateFilter != null ||
          _selectedStatusFilter != null)
        cupertino.CupertinoButton(
          padding: const EdgeInsets.symmetric(
            horizontal: IOSSpacing.md - 4,
            vertical: IOSSpacing.xs + 2,
          ),
          onPressed: () {
            HapticFeedback.lightImpact();
            setState(() {
              _selectedPeriodFilter = null;
              _selectedTemplateFilter = null;
              _selectedStatusFilter = null;
            });
          },
          minimumSize: Size.zero,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                cupertino.CupertinoIcons.clear,
                size: 14,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
              SizedBox(width: IOSSpacing.xsOf(context)),
              Text(
                localizations.clear,
                style: IOSTextStyle.footnote(context),
              ),
            ],
          ),
        ),
    ];
  }

  Widget _buildIOSFilterButton({
    required String label,
    required String? value,
    required List<String?> options,
    required VoidCallback onTap,
    bool isStatusFilter = false,
  }) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final hasSelection = value != null;

    String displayText = label;
    if (hasSelection) {
      displayText = isStatusFilter
          ? localizations.localizeStatus(value)
          : value;
    }

    return cupertino.CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      minimumSize: Size.zero,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: IOSSpacing.md - 6, vertical: IOSSpacing.xs + 2),
        decoration: BoxDecoration(
          color: hasSelection
              ? IOSColors.getSystemBlue(context).withValues(alpha: 0.1)
              : theme.colorScheme.onSurface.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(6),
          border: hasSelection
              ? Border.all(
                  color: IOSColors.getSystemBlue(context).withValues(alpha: 0.3),
                  width: 0.5,
                )
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: Text(
                displayText,
                style: IOSTextStyle.footnote(context).copyWith(
                  fontWeight: hasSelection ? FontWeight.w600 : FontWeight.w400,
                  color: hasSelection
                      ? IOSColors.getSystemBlue(context)
                      : theme.colorScheme.onSurface.withValues(alpha: 0.7),
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            SizedBox(width: IOSSpacing.xsOf(context)),
            Icon(
              cupertino.CupertinoIcons.chevron_down,
              size: 12,
              color: hasSelection
                  ? IOSColors.getSystemBlue(context)
                  : theme.colorScheme.onSurface.withValues(alpha: 0.4),
            ),
          ],
        ),
      ),
    );
  }

  void _showIOSFilterPicker({
    required BuildContext context,
    required String title,
    required List<String?> options,
    required String? selectedValue,
    required Function(String?) onSelected,
    required AppLocalizations localizations,
    bool isStatusFilter = false,
  }) {
    HapticFeedback.selectionClick();

    cupertino.showCupertinoModalPopup(
      context: context,
      builder: (context) => cupertino.CupertinoActionSheet(
        title: Text(
          title,
          style: IOSTextStyle.headline(context),
        ),
        actions: [
          // "All" option
          cupertino.CupertinoActionSheetAction(
            onPressed: () {
              Navigator.of(context).pop();
              onSelected(null);
            },
            child: Text(
              localizations.allYears.split(' ')[0],
              style: IOSTextStyle.body(context).copyWith(
                color: selectedValue == null
                    ? IOSColors.getSystemBlue(context)
                    : Theme.of(context).colorScheme.onSurface,
                fontWeight: selectedValue == null ? FontWeight.w600 : FontWeight.w400,
              ),
            ),
          ),
          // Options
          ...options.map((option) {
            final displayText = isStatusFilter
                ? (option != null ? localizations.localizeStatus(option) : localizations.nA)
                : (option ?? localizations.nA);
            final isSelected = option == selectedValue;

            return cupertino.CupertinoActionSheetAction(
              onPressed: () {
                Navigator.of(context).pop();
                onSelected(option);
              },
              child: Text(
                displayText,
                style: IOSTextStyle.body(context).copyWith(
                  color: isSelected
                      ? IOSColors.getSystemBlue(context)
                      : Theme.of(context).colorScheme.onSurface,
                  fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                ),
              ),
            );
          }),
        ],
        cancelButton: cupertino.CupertinoActionSheetAction(
          isDestructiveAction: false,
          onPressed: () => Navigator.of(context).pop(),
          child: Text(
            localizations.cancel,
            style: IOSTextStyle.body(context).copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPastAssignmentCard(Assignment assignment, int index) {
    return AppFadeInUp(
      staggerIndex: index,
      child: AssignmentCard(
        assignment: assignment,
        onTap: () {
          HapticFeedback.lightImpact();
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: AppRoutes.formEntry(assignment.id),
          );
        },
      ),
    );
  }

  void _showEntitySelector(BuildContext context, DashboardProvider provider) {
    EntitySelectorBottomSheet.show(context, provider);
  }

  Widget _buildSectionHeader({
    required String title,
    required IconData icon,
    required Color color,
    int? count,
  }) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        IOSSpacing.lgOf(context),
        IOSSpacing.xlOf(context),
        IOSSpacing.lgOf(context),
        IOSSpacing.mdOf(context),
      ),
      child: Row(
        children: [
          Text(
            title.toUpperCase(),
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            ),
          ),
          if (count != null && count > 0) ...[
            SizedBox(width: IOSSpacing.smOf(context)),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: IOSSpacing.xs + 2, vertical: IOSSpacing.xs / 2),
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '$count',
                style: IOSTextStyle.caption2(context).copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer2<AuthProvider, LanguageProvider>(
      builder: (context, authProvider, languageProvider, child) {
        final localizations = AppLocalizations.of(context)!;

        // Listen to language changes and reload dashboard data
        if (_previousLanguage != null &&
            _previousLanguage != languageProvider.currentLanguage) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            // Language changed - clear cache and reload data
            _previousLanguage = languageProvider.currentLanguage;
            final dashboardProvider =
                Provider.of<DashboardProvider>(context, listen: false);
            // Clear cache to force fresh API data with new language
            dashboardProvider.clearCache();
            // Reload data with force refresh to get new language content
            _loadData(forceRefresh: true);
          });
        }

        return Scaffold(
          appBar: AppAppBar(
            title: localizations.dashboard,
          ),
          backgroundColor: IOSColors.getGroupedBackground(context), // iOS grouped background
          body: ColoredBox(
            color: IOSColors.getGroupedBackground(context),
            child: RefreshIndicator(
              onRefresh: () async {
                HapticFeedback.lightImpact();
                if (_animationController.isAnimating) {
                  _animationController.stop();
                }
                _animationController.reset();
                await _loadData();
                _animationController.forward();
              },
              color: IOSColors.getSystemBlue(context),
              strokeWidth: 2.5,
              displacement: 40,
              backgroundColor: Theme.of(context).scaffoldBackgroundColor,
              child: Consumer<DashboardProvider>(
                builder: (context, provider, child) {
                  // Show loading if currently loading OR if we haven't completed first load yet
                  final bool shouldShowLoading = provider.isLoading || !_hasLoadedOnce;

                  if (shouldShowLoading &&
                      provider.currentAssignments.isEmpty &&
                      provider.pastAssignments.isEmpty) {
                    return AppLoadingIndicator(
                      message: localizations.loadingDashboard,
                      color: Color(AppConstants.ifrcRed),
                    );
                  }

                  if (provider.error != null &&
                      provider.currentAssignments.isEmpty &&
                      provider.pastAssignments.isEmpty &&
                      _hasLoadedOnce) {
                    return AppErrorState(
                      message: provider.error,
                      onRetry: () {
                        provider.clearError();
                        _loadData();
                      },
                      retryLabel: localizations.retry,
                    );
                  }

                  return FadeTransition(
                    opacity: _fadeAnimation,
                    child: SingleChildScrollView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: EdgeInsets.zero,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          // National Society Title - Always show if we have any entity info
                          if (provider.selectedEntity != null ||
                              provider.entities.isNotEmpty)
                            Builder(
                              builder: (context) {
                                // Get entity from selectedEntity or first entity
                                final entity = provider.selectedEntity ??
                                    provider.entities.first;
                                final hasMultipleEntities =
                                    provider.entities.length > 1;
                                final theme = Theme.of(context);

                                return GestureDetector(
                                  onTap: hasMultipleEntities
                                      ? () {
                                          HapticFeedback.lightImpact();
                                          _showEntitySelector(
                                              context, provider);
                                        }
                                      : null,
                                  child: Container(
                                    margin: const EdgeInsets.fromLTRB(
                                        IOSSpacing.lg, IOSSpacing.lg, IOSSpacing.lg, IOSSpacing.md),
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: IOSSpacing.md, vertical: IOSSpacing.sm + 6),
                                    decoration: BoxDecoration(
                                      color: theme.cardTheme.color ??
                                          theme.colorScheme.surface,
                                      borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusLargeOf(context)),
                                    ),
                                    child: Row(
                                      children: [
                                        Icon(
                                          Icons.location_on_rounded,
                                          size: 20,
                                          color: theme.colorScheme.onSurface
                                              .withValues(alpha: 0.7),
                                        ),
                                        SizedBox(width: IOSSpacing.mdOf(context) - 4),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                entity.displayLabel,
                                                style: IOSTextStyle.callout(context).copyWith(
                                                  fontWeight: FontWeight.w600,
                                                  color: theme.colorScheme
                                                      .onSurface,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                        if (hasMultipleEntities)
                                          Icon(
                                            Icons.chevron_right_rounded,
                                            color: theme.colorScheme.onSurface
                                                .withValues(alpha: 0.4),
                                            size: 20,
                                          ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),

                          // Current assignments (same bucket as dashboard.html current_assignments)
                          if (provider.currentAssignments.isNotEmpty ||
                              provider.pastAssignments.isNotEmpty) ...[
                            _buildSectionHeader(
                              title: localizations.currentAssignments,
                              icon: Icons.assignment_rounded,
                              color: context.isDarkTheme
                                  ? Theme.of(context)
                                      .colorScheme.tertiary
                                  : context.navyIconColor,
                              count: provider.currentAssignments.isEmpty
                                  ? null
                                  : provider.currentAssignments.length,
                            ),
                            if (provider.currentAssignments.isNotEmpty)
                              Padding(
                                padding: EdgeInsets.symmetric(
                                    horizontal: IOSSpacing.lgOf(context)),
                                child: Column(
                                  children: provider.currentAssignments
                                      .asMap()
                                      .entries
                                      .map((entry) {
                                    final index = entry.key;
                                    final assignment = entry.value;

                                    return AppFadeInUp(
                                      staggerIndex: index,
                                      child: AssignmentCard(
                                        assignment: assignment,
                                        onTap: () {
                                          HapticFeedback.lightImpact();
                                          Navigator.of(context).pushNamed(
                                            AppRoutes.webview,
                                            arguments: AppRoutes.formEntry(
                                                assignment.id),
                                          );
                                        },
                                        showEnterDataButton:
                                            _shouldShowEnterDataButton(
                                          authProvider.user?.role,
                                          assignment,
                                        ),
                                        enterDataButtonText:
                                            localizations.enterData,
                                        onEnterData: () {
                                          HapticFeedback.mediumImpact();
                                          Navigator.of(context).pushNamed(
                                            AppRoutes.webview,
                                            arguments: AppRoutes.formEntry(
                                                assignment.id),
                                          );
                                        },
                                      ),
                                    );
                                  }).toList(),
                                ),
                              )
                            else if (provider.pastAssignments.isNotEmpty)
                              Padding(
                                padding: EdgeInsets.fromLTRB(
                                  IOSSpacing.lgOf(context),
                                  0,
                                  IOSSpacing.lgOf(context),
                                  IOSSpacing.lgOf(context),
                                ),
                                child: Column(
                                  children: [
                                    Icon(
                                      Icons.check_circle_outline_rounded,
                                      size: 48,
                                      color: Theme.of(context)
                                          .colorScheme
                                          .onSurface
                                          .withValues(alpha: 0.35),
                                    ),
                                    SizedBox(height: IOSSpacing.mdOf(context)),
                                    Text(
                                      localizations.noAssignmentsYet,
                                      style: IOSTextStyle.subheadline(context)
                                          .copyWith(
                                        fontWeight: FontWeight.w600,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withValues(alpha: 0.75),
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                    SizedBox(height: IOSSpacing.smOf(context)),
                                    Text(
                                      localizations.newAssignmentsWillAppear,
                                      style: IOSTextStyle.footnote(context)
                                          .copyWith(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withValues(alpha: 0.55),
                                        height: 1.35,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              ),
                            if (provider.currentAssignments.isNotEmpty)
                              const SizedBox(height: IOSSpacing.xxl)
                            else if (provider.pastAssignments.isNotEmpty)
                              SizedBox(height: IOSSpacing.mdOf(context)),
                          ],

                          // Past assignments (dashboard.html: collapsible + slicers + one list)
                          if (provider.pastAssignments.isNotEmpty) ...[
                            _buildPastAssignmentsSection(provider),
                          ],

                          // Empty State - only show after we've loaded at least once
                          if (provider.currentAssignments.isEmpty &&
                              provider.pastAssignments.isEmpty &&
                              !provider.isLoading &&
                              _hasLoadedOnce &&
                              provider.error == null)
                            SizedBox(
                              height: MediaQuery.of(context).size.height * 0.6,
                              child: Center(
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(
                                      horizontal: 40),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment:
                                        CrossAxisAlignment.center,
                                    children: [
                          Icon(
                            Icons.inbox_rounded,
                            size: 72,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurface
                                .withValues(alpha: 0.25),
                          ),
                          SizedBox(height: IOSSpacing.xlOf(context)),
                          Text(
                            localizations.noAssignmentsYet,
                            style: IOSTextStyle.title2(context),
                            textAlign: TextAlign.center,
                          ),
                          SizedBox(height: IOSSpacing.smOf(context)),
                          Text(
                            localizations.newAssignmentsWillAppear,
                            style: IOSTextStyle.subheadline(context).copyWith(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withValues(alpha: 0.6),
                              height: 1.4,
                            ),
                            textAlign: TextAlign.center,
                          ),
                                    ],
                                  ),
                                ),
                              ),
                            ),

                          const SizedBox(height: 80), // Space for FAB
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        );
      },
    );
  }
}

