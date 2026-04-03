import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/dashboard_provider.dart';
import '../../providers/shared/notification_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../widgets/assignment_card.dart';
import '../../widgets/admin_drawer.dart';
import '../../widgets/app_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/ios_constants.dart';
import '../../models/shared/assignment.dart';
import '../../models/shared/entity.dart';
import '../../l10n/app_localizations.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/error_state.dart';

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

  // Track expanded cards
  final Set<int> _expandedCardIds = <int>{};

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

  bool _shouldShowEnterDataButton(String? userRole, String assignmentStatus) {
    // For admins and system managers: always show
    if (userRole == 'admin' || userRole == 'system_manager') {
      return true;
    }

    // For focal points: show only when status is NOT "Submitted", "Approved", or "Requires Revision"
    if (userRole == 'focal_point') {
      final statusLower = assignmentStatus.toLowerCase();
      return statusLower != 'submitted' &&
          statusLower != 'approved' &&
          statusLower != 'requires revision';
    }

    // For other roles: don't show
    return false;
  }

  Widget _buildStatsCard({
    required String title,
    required String value,
    required Color color,
    required Color backgroundColor,
  }) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Expanded(
      child: Container(
        margin: EdgeInsets.symmetric(horizontal: IOSSpacing.xsOf(context)),
        padding: EdgeInsets.symmetric(
          horizontal: IOSSpacing.mdOf(context),
          vertical: IOSSpacing.mdOf(context),
        ),
        decoration: BoxDecoration(
          color: isDark
              ? IOSColors.secondarySystemBackgroundDark
              : IOSColors.secondarySystemBackground,
          borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusMediumOf(context)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.baseline,
          textBaseline: TextBaseline.alphabetic,
          children: [
            Text(
              value,
              style: IOSTextStyle.title3(context).copyWith(
                color: color,
                height: 1.0,
                fontWeight: FontWeight.w700,
              ),
            ),
            SizedBox(width: IOSSpacing.xsOf(context)),
            Flexible(
              child: Text(
                title,
                style: IOSTextStyle.caption1(context).copyWith(
                  color: theme.colorScheme.onSurface.withOpacity(0.6),
                  fontWeight: FontWeight.w500,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // Build past assignments section with grouping and filters (like HTML)
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

    // Group by status (like HTML: Approved and Requires Revision)
    // Use case-insensitive comparison for status matching
    final approvedAssignments = filteredAssignments
        .where((a) => a.status.toLowerCase() == 'approved')
        .toList();
    final revisionAssignments = filteredAssignments
        .where((a) => a.status.toLowerCase() == 'requires revision')
        .toList();
    final otherAssignments = filteredAssignments
        .where((a) =>
            a.status.toLowerCase() != 'approved' &&
            a.status.toLowerCase() != 'requires revision')
        .toList();

    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 0),
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
                  color: theme.colorScheme.onSurface.withOpacity(0.6),
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
                  color: theme.colorScheme.onSurface.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusSmallOf(context)),
                ),
                child: Text(
                  '${filteredAssignments.length}',
                  style: IOSTextStyle.caption2(context).copyWith(
                    color: theme.colorScheme.onSurface.withOpacity(0.8),
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

            // Grouped Assignments
            Padding(
              padding: const EdgeInsets.fromLTRB(0, 0, 0, IOSSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Approved Assignments Group
                  if (approvedAssignments.isNotEmpty) ...[
                    _buildStatusGroupHeader(
                      localizations.approved,
                      approvedAssignments.length,
                      const Color(AppConstants.successColor),
                      Icons.check_circle_rounded,
                    ),
                    Container(
                      color: Theme.of(context).cardTheme.color ??
                          Theme.of(context).colorScheme.surface,
                      child: Column(
                        children: approvedAssignments.asMap().entries.map(
                          (entry) {
                            final index = entry.key;
                            final isLast =
                                index == approvedAssignments.length - 1;
                            return _buildPastAssignmentCard(
                              entry.value,
                              index,
                              Theme.of(context).cardTheme.color ??
                                  Theme.of(context).colorScheme.surface,
                              isLast,
                            );
                          },
                        ).toList(),
                      ),
                    ),
                    SizedBox(height: IOSSpacing.xlOf(context)),
                  ],

                  // Requires Revision Group
                  if (revisionAssignments.isNotEmpty) ...[
                    _buildStatusGroupHeader(
                      localizations.requiresRevision,
                      revisionAssignments.length,
                      const Color(AppConstants.warningColor),
                      Icons.warning_rounded,
                    ),
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
                      decoration: BoxDecoration(
                        color: Theme.of(context).cardTheme.color ??
                            Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusLargeOf(context)),
                        boxShadow: Theme.of(context).brightness == Brightness.dark
                            ? []
                            : [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.02),
                                  blurRadius: 8,
                                  offset: const Offset(0, 1),
                                ),
                              ],
                      ),
                      child: Column(
                        children: revisionAssignments.asMap().entries.map(
                          (entry) {
                            final index = entry.key;
                            final isLast =
                                index == revisionAssignments.length - 1;
                            return _buildPastAssignmentCard(
                              entry.value,
                              index,
                              Theme.of(context).cardTheme.color ??
                                  Theme.of(context).colorScheme.surface,
                              isLast,
                            );
                          },
                        ).toList(),
                      ),
                    ),
                    SizedBox(height: IOSSpacing.xlOf(context)),
                  ],

                  // Other Statuses Group
                  if (otherAssignments.isNotEmpty) ...[
                    _buildStatusGroupHeader(
                      localizations.other,
                      otherAssignments.length,
                      const Color(AppConstants.textSecondary),
                      Icons.info_rounded,
                    ),
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
                      decoration: BoxDecoration(
                        color: Theme.of(context).cardTheme.color ??
                            Theme.of(context).colorScheme.surface,
                        borderRadius: BorderRadius.circular(IOSDimensions.borderRadiusLargeOf(context)),
                        boxShadow: Theme.of(context).brightness == Brightness.dark
                            ? []
                            : [
                                BoxShadow(
                                  color: Colors.black.withOpacity(0.02),
                                  blurRadius: 8,
                                  offset: const Offset(0, 1),
                                ),
                              ],
                      ),
                      child: Column(
                        children: otherAssignments.asMap().entries.map(
                          (entry) {
                            final index = entry.key;
                            final isLast =
                                index == otherAssignments.length - 1;
                            return _buildPastAssignmentCard(
                              entry.value,
                              index,
                              Theme.of(context).cardTheme.color ??
                                  Theme.of(context).colorScheme.surface,
                              isLast,
                            );
                          },
                        ).toList(),
                      ),
                    ),
                    SizedBox(height: IOSSpacing.xlOf(context)),
                  ],

                  // Empty filtered state
                  if (filteredAssignments.isEmpty)
                    Container(
                      margin: const EdgeInsets.symmetric(horizontal: IOSSpacing.lg),
                      padding: EdgeInsets.all(IOSSpacing.xxl),
                      child: Column(
                        children: [
                          Icon(
                            Icons.filter_alt_off_rounded,
                            size: 48,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurface
                                .withOpacity(0.4),
                          ),
                          SizedBox(height: IOSSpacing.mdOf(context)),
                          Text(
                            localizations.noAssignmentsMatchFilters,
                            style: IOSTextStyle.subheadline(context).copyWith(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withOpacity(0.6),
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
          minSize: 0,
          onPressed: () {
            HapticFeedback.lightImpact();
            setState(() {
              _selectedPeriodFilter = null;
              _selectedTemplateFilter = null;
              _selectedStatusFilter = null;
            });
          },
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                cupertino.CupertinoIcons.clear,
                size: 14,
                color: theme.colorScheme.onSurface.withOpacity(0.6),
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
    if (hasSelection && value != null) {
      displayText = isStatusFilter
          ? localizations.localizeStatus(value)
          : value;
    }

    return cupertino.CupertinoButton(
      padding: EdgeInsets.zero,
      minSize: 0,
      onPressed: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: IOSSpacing.md - 6, vertical: IOSSpacing.xs + 2),
        decoration: BoxDecoration(
          color: hasSelection
              ? IOSColors.getSystemBlue(context).withOpacity(0.1)
              : theme.colorScheme.onSurface.withOpacity(0.06),
          borderRadius: BorderRadius.circular(6),
          border: hasSelection
              ? Border.all(
                  color: IOSColors.getSystemBlue(context).withOpacity(0.3),
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
                      : theme.colorScheme.onSurface.withOpacity(0.7),
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
                  : theme.colorScheme.onSurface.withOpacity(0.4),
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
            'Cancel', // iOS standard cancel text
            style: IOSTextStyle.body(context).copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStatusGroupHeader(
    String title,
    int count,
    Color color,
    IconData icon,
  ) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(IOSSpacing.lg, IOSSpacing.sm, IOSSpacing.lg, IOSSpacing.md - 4),
      child: Row(
        children: [
          Icon(
            icon,
            size: 16,
            color: color,
          ),
          SizedBox(width: IOSSpacing.smOf(context)),
          Text(
            title,
            style: IOSTextStyle.callout(context).copyWith(
              fontWeight: FontWeight.w600,
              color: theme.colorScheme.onSurface,
              letterSpacing: -0.3,
            ),
          ),
          SizedBox(width: IOSSpacing.sm),
          Container(
              padding: EdgeInsets.symmetric(
                horizontal: IOSSpacing.xsOf(context) + 2,
                vertical: IOSSpacing.xsOf(context) / 2,
              ),
            decoration: BoxDecoration(
              color: color.withOpacity(0.15),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              '$count',
              style: IOSTextStyle.caption1(context).copyWith(
                color: color,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPastAssignmentCard(
    Assignment assignment,
    int index,
    Color backgroundColor,
    bool isLast,
  ) {
    final isExpanded = _expandedCardIds.contains(assignment.id);

    return Column(
      children: [
        AssignmentCard(
          assignment: assignment,
          isExpanded: isExpanded,
          onToggleExpand: () {
            HapticFeedback.selectionClick();
            setState(() {
              if (isExpanded) {
                _expandedCardIds.remove(assignment.id);
              } else {
                _expandedCardIds.add(assignment.id);
              }
            });
          },
          onTap: () {
            HapticFeedback.lightImpact();
            Navigator.of(context).pushNamed(
              AppRoutes.webview,
              arguments: AppRoutes.formEntry(assignment.id),
            );
          },
        ),
        if (!isLast)
          Divider(
            height: 1,
            thickness: 0.5,
            indent: IOSSpacing.md,
            endIndent: IOSSpacing.md,
            color: Theme.of(context).dividerColor.withOpacity(0.5),
          ),
      ],
    );
  }

  void _showEntitySelector(BuildContext context, DashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    // Add haptic feedback
    HapticFeedback.selectionClick();

    cupertino.showCupertinoModalPopup(
      context: context,
      builder: (context) => _EntitySelectorBottomSheet(
        provider: provider,
        theme: theme,
        localizations: localizations,
      ),
    );
  }

  void _triggerHapticSelection() {
    HapticFeedback.selectionClick();
  }

  void _triggerHapticLight() {
    HapticFeedback.lightImpact();
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
              color: theme.colorScheme.onSurface.withOpacity(0.6),
            ),
          ),
          if (count != null && count > 0) ...[
            SizedBox(width: IOSSpacing.smOf(context)),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: IOSSpacing.xs + 2, vertical: IOSSpacing.xs / 2),
              decoration: BoxDecoration(
                color: theme.colorScheme.onSurface.withOpacity(0.15),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                '$count',
                style: IOSTextStyle.caption2(context).copyWith(
                  color: theme.colorScheme.onSurface.withOpacity(0.8),
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

        final theme = Theme.of(context);
        return Scaffold(
          appBar: AppAppBar(
            title: localizations.dashboard,
          ),
          backgroundColor: IOSColors.getGroupedBackground(context), // iOS grouped background
          body: Container(
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
                                              .withOpacity(0.7),
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
                                                .withOpacity(0.4),
                                            size: 20,
                                          ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                            ),
                          // Stats Overview Cards
                          if (provider.currentAssignments.isNotEmpty ||
                              provider.pastAssignments.isNotEmpty)
                            Container(
                              margin: EdgeInsets.fromLTRB(
                                IOSSpacing.lgOf(context),
                                0,
                                IOSSpacing.lgOf(context),
                                IOSSpacing.xlOf(context) + 4,
                              ),
                              child: Row(
                                children: [
                                  _buildStatsCard(
                                    title: localizations.active,
                                    value: '${provider.currentAssignments.length}',
                                    color: Theme.of(context).brightness ==
                                            Brightness.dark
                                        ? Colors.blue.shade400
                                        : context.navyTextColor,
                                    backgroundColor: Colors.transparent,
                                  ),
                                  _buildStatsCard(
                                    title: localizations.completed,
                                    value: '${provider.pastAssignments.length}',
                                    color: const Color(
                                        AppConstants.successColor),
                                    backgroundColor: Colors.transparent,
                                  ),
                                ],
                              ),
                            ),

                          // Current Assignments Section
                          if (provider.currentAssignments.isNotEmpty) ...[
                            _buildSectionHeader(
                              title: localizations.currentAssignments,
                              icon: Icons.assignment_rounded,
                              color: Theme.of(context).brightness ==
                                      Brightness.dark
                                  ? Colors.blue.shade300
                                  : context.navyIconColor,
                              count: provider.currentAssignments.length,
                            ),
                            Container(
                              color: Theme.of(context).cardTheme.color ??
                                  Theme.of(context).colorScheme.surface,
                              child: Column(
                                children: provider.currentAssignments
                                    .asMap()
                                    .entries
                                    .map((entry) {
                                  final index = entry.key;
                                  final assignment = entry.value;
                                  final isExpanded =
                                      _expandedCardIds.contains(assignment.id);
                                  final isLast = index ==
                                      provider.currentAssignments.length - 1;

                                  return Column(
                                    children: [
                                      AssignmentCard(
                                        assignment: assignment,
                                        isExpanded: isExpanded,
                                        onToggleExpand: () {
                                          HapticFeedback.selectionClick();
                                          setState(() {
                                            if (isExpanded) {
                                              _expandedCardIds
                                                  .remove(assignment.id);
                                            } else {
                                              _expandedCardIds
                                                  .add(assignment.id);
                                            }
                                          });
                                        },
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
                                          assignment.status,
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
                                      if (!isLast)
                                      Divider(
                                        height: 0.5,
                                        thickness: 0.5,
                                        indent: IOSSpacing.lg,
                                        endIndent: IOSSpacing.lg,
                                          color: Theme.of(context)
                                              .dividerColor
                                              .withOpacity(0.5),
                                        ),
                                    ],
                                  );
                                }).toList(),
                              ),
                            ),
                            SizedBox(height: IOSSpacing.xxl),
                          ],

                          // Past Assignments Section (Grouped like HTML)
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
                                .withOpacity(0.25),
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
                                  .withOpacity(0.6),
                              height: 1.4,
                            ),
                            textAlign: TextAlign.center,
                          ),
                                    ],
                                  ),
                                ),
                              ),
                            ),

                          SizedBox(height: 80), // Space for FAB
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

// Helper class to represent either a section header or an entity in the list
class _EntityListItem {
  final bool isHeader;
  final String? entityType;
  final Entity? entity;

  _EntityListItem({
    required this.isHeader,
    this.entityType,
    this.entity,
  });
}

// Separate StatefulWidget to properly manage state in the bottom sheet
class _EntitySelectorBottomSheet extends StatefulWidget {
  final DashboardProvider provider;
  final ThemeData theme;
  final AppLocalizations localizations;

  const _EntitySelectorBottomSheet({
    required this.provider,
    required this.theme,
    required this.localizations,
  });

  @override
  State<_EntitySelectorBottomSheet> createState() =>
      _EntitySelectorBottomSheetState();
}

class _EntitySelectorBottomSheetState
    extends State<_EntitySelectorBottomSheet> {
  late TextEditingController _searchController;
  late Map<String, List<Entity>> _groupedEntities;

  @override
  void initState() {
    super.initState();
    _searchController = TextEditingController();
    _groupedEntities = _groupEntitiesByType(widget.provider.entities);
    _searchController.addListener(_onSearchChanged);
  }

  @override
  void dispose() {
    _searchController.removeListener(_onSearchChanged);
    _searchController.dispose();
    super.dispose();
  }

  Map<String, List<Entity>> _groupEntitiesByType(List<Entity> entities) {
    final Map<String, List<Entity>> grouped = {};

    for (final entity in entities) {
      final type = entity.entityType;
      if (!grouped.containsKey(type)) {
        grouped[type] = [];
      }
      grouped[type]!.add(entity);
    }

    // Sort entities within each group alphabetically by displayLabel
    for (final type in grouped.keys) {
      grouped[type]!.sort((a, b) => a.displayLabel.compareTo(b.displayLabel));
    }

    return grouped;
  }

  void _onSearchChanged() {
    if (!mounted) return;
    final query = _searchController.text.toLowerCase();
    setState(() {
      if (query.isEmpty) {
        _groupedEntities = _groupEntitiesByType(widget.provider.entities);
      } else {
        final filtered = widget.provider.entities.where((entity) {
          return entity.displayLabel.toLowerCase().contains(query) ||
              entity.name.toLowerCase().contains(query);
        }).toList();
        _groupedEntities = _groupEntitiesByType(filtered);
      }
    });
  }

  List<String> get _sortedEntityTypes {
    final types = _groupedEntities.keys.toList();
    // Sort entity types in a logical order
    final typeOrder = {
      'country': 0,
      'ns_branch': 1,
      'ns_subbranch': 2,
      'ns_localunit': 3,
      'division': 4,
      'department': 5,
    };
    types.sort((a, b) {
      final orderA = typeOrder[a.toLowerCase()] ?? 999;
      final orderB = typeOrder[b.toLowerCase()] ?? 999;
      if (orderA != orderB) {
        return orderA.compareTo(orderB);
      }
      return a.compareTo(b);
    });
    return types;
  }

  List<_EntityListItem> get _flatItemList {
    final List<_EntityListItem> items = [];
    for (final sectionType in _sortedEntityTypes) {
      // Add section header
      items.add(_EntityListItem(isHeader: true, entityType: sectionType));
      // Add entities in this section
      final entities = _groupedEntities[sectionType]!;
      for (final entity in entities) {
        items.add(_EntityListItem(isHeader: false, entity: entity));
      }
    }
    return items;
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
      decoration: BoxDecoration(
        color: widget.theme.scaffoldBackgroundColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          // Handle bar
          Container(
            margin: const EdgeInsets.only(top: 8, bottom: 4),
            width: 36,
            height: 5,
            decoration: BoxDecoration(
              color: widget.theme.colorScheme.onSurface.withOpacity(0.2),
              borderRadius: BorderRadius.circular(2.5),
            ),
          ),
          // Header
          Padding(
            padding: EdgeInsets.fromLTRB(
              IOSSpacing.lgOf(context),
              IOSSpacing.mdOf(context) - 4,
              IOSSpacing.mdOf(context),
              IOSSpacing.smOf(context),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    localizations.entities,
                    style: IOSTextStyle.title1(context),
                  ),
                ),
                Semantics(
                  label: localizations.close,
                  button: true,
                  child: IconButton(
                    icon: Icon(
                      Icons.close_rounded,
                      color: widget.theme.colorScheme.onSurface,
                      size: 24,
                    ),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ),
              ],
            ),
          ),
          // Search field
          Padding(
            padding: EdgeInsets.fromLTRB(
              IOSSpacing.lgOf(context),
              IOSSpacing.smOf(context),
              IOSSpacing.lgOf(context),
              IOSSpacing.mdOf(context) - 4,
            ),
            child: cupertino.CupertinoSearchTextField(
              controller: _searchController,
              placeholder: 'Search...',
              placeholderStyle: IOSTextStyle.subheadline(context).copyWith(
                color: widget.theme.colorScheme.onSurface.withOpacity(0.4),
              ),
              style: IOSTextStyle.subheadline(context).copyWith(
                color: widget.theme.colorScheme.onSurface,
              ),
              backgroundColor: widget.theme.colorScheme.onSurface.withOpacity(0.06),
              itemColor: widget.theme.colorScheme.onSurface,
            ),
          ),
          // Entity list
          Expanded(
            child: _groupedEntities.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.search_off,
                          size: 48,
                          color: widget.theme.colorScheme.onSurface
                              .withOpacity(0.4),
                        ),
                        SizedBox(height: IOSSpacing.mdOf(context)),
                        Text(
                          'No results found',
                          style: IOSTextStyle.subheadline(context).copyWith(
                            color: widget.theme.textTheme.bodyMedium?.color ??
                                widget.theme.colorScheme.onSurface
                                    .withOpacity(0.6),
                          ),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding:
                        const EdgeInsets.symmetric(horizontal: IOSSpacing.md, vertical: IOSSpacing.sm),
                    itemCount: _flatItemList.length,
                    itemBuilder: (context, index) {
                      final item = _flatItemList[index];

                      // If this is a section header
                      if (item.isHeader && item.entityType != null) {
                        return _buildSectionHeader(item.entityType!);
                      }

                      // If this is an entity item
                      if (!item.isHeader && item.entity != null) {
                        final entity = item.entity!;
                        final isSelected =
                            widget.provider.selectedEntity?.entityType ==
                                    entity.entityType &&
                                widget.provider.selectedEntity?.entityId ==
                                    entity.entityId;

                        return Material(
                          color: Colors.transparent,
                          child: InkWell(
                            onTap: () {
                              // Add haptic feedback
                              HapticFeedback.selectionClick();

                              // Get the entity before closing to avoid accessing after dispose
                              final entityToSelect = entity;
                              final providerToUse = widget.provider;

                              // Close bottom sheet first
                              Navigator.of(context).pop();

                              // Select entity after navigation completes
                              WidgetsBinding.instance.addPostFrameCallback((_) {
                                providerToUse.selectEntity(entityToSelect);
                              });
                            },
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                  vertical: IOSSpacing.sm + 6, horizontal: IOSSpacing.lg),
                              decoration: BoxDecoration(
                                border: Border(
                                  bottom: BorderSide(
                                    color: widget.theme.dividerColor
                                        .withOpacity(0.5),
                                    width: 0.5,
                                  ),
                                ),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: Text(
                                      entity.displayLabel,
                                      style: IOSTextStyle.callout(context).copyWith(
                                        fontWeight: isSelected
                                            ? FontWeight.w600
                                            : FontWeight.w400,
                                        color: isSelected
                                            ? (widget.theme.brightness ==
                                                    Brightness.dark
                                                ? Colors.blue.shade300
                                                : context.navyTextColor)
                                            : widget.theme.colorScheme.onSurface,
                                      ),
                                    ),
                                  ),
                                  if (isSelected)
                                    Icon(
                                      Icons.check_rounded,
                                      color:
                                          widget.theme.brightness == Brightness.dark
                                              ? Colors.blue.shade300
                                              : context.navyIconColor,
                                      size: 22,
                                    ),
                                ],
                              ),
                            ),
                          ),
                        );
                      }

                      // Fallback (should not happen)
                      return const SizedBox.shrink();
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader(String entityType) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        IOSSpacing.lgOf(context),
        IOSSpacing.mdOf(context) + 4,
        IOSSpacing.lgOf(context),
        IOSSpacing.smOf(context),
      ),
      decoration: BoxDecoration(
        color: widget.theme.colorScheme.onSurface.withOpacity(0.04),
        border: Border(
          bottom: BorderSide(
            color: widget.theme.dividerColor.withOpacity(0.3),
            width: 0.5,
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(
            _getEntityIcon(entityType),
            size: 16,
            color: widget.theme.colorScheme.onSurface.withOpacity(0.6),
          ),
          SizedBox(width: IOSSpacing.smOf(context)),
          Text(
            _getEntityTypeLabel(entityType).toUpperCase(),
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              color: widget.theme.colorScheme.onSurface.withOpacity(0.6),
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
              color: widget.theme.colorScheme.onSurface.withOpacity(0.15),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              '${_groupedEntities[entityType]?.length ?? 0}',
              style: IOSTextStyle.caption2(context).copyWith(
                color: widget.theme.colorScheme.onSurface.withOpacity(0.8),
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  IconData _getEntityIcon(String entityType) {
    switch (entityType.toLowerCase()) {
      case 'country':
        return Icons.flag;
      case 'ns_branch':
        return Icons.account_tree;
      case 'ns_subbranch':
        return Icons.call_split;
      case 'ns_localunit':
        return Icons.location_on;
      case 'division':
        return Icons.business;
      case 'department':
        return Icons.work;
      default:
        return Icons.folder;
    }
  }

  String _getEntityTypeLabel(String entityType) {
    switch (entityType.toLowerCase()) {
      case 'country':
        return 'Country';
      case 'ns_branch':
        return 'NS Branch';
      case 'ns_subbranch':
        return 'NS Sub-Branch';
      case 'ns_localunit':
        return 'NS Local Unit';
      case 'division':
        return 'Division';
      case 'department':
        return 'Department';
      default:
        return entityType.toUpperCase();
    }
  }
}
