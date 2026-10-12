import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/dashboard_provider.dart';
import '../../providers/shared/notification_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../providers/shared/offline_provider.dart';
import '../../widgets/dashboard_grouped_assignment_card.dart';
import '../../config/routes.dart';
import '../../theme/grouped_dashboard_palette.dart';
import '../../theme/grouped_sheet_style.dart';
import '../../widgets/sheets/native_modal_sheet.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../models/shared/assignment.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/debug_logger.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/error_state.dart';
import '../../widgets/app_fade_in_up.dart';
import '../../widgets/dashboard_focal_points_section.dart';
import '../../widgets/entity_selector_bottom_sheet.dart';
import '../../services/assignment_offline_bundle_service.dart';
import '../../services/offline/offline_forms_controller.dart';
import '../../utils/network_availability.dart';
import '../public/webview_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animationController;
  late Animation<double> _fadeAnimation;

  // Past assignments stay collapsed until the user opens them (matches Backoffice).
  bool _pastAssignmentsExpanded = false;

  // Filter state for past assignments
  String? _selectedPeriodFilter;
  String? _selectedTemplateFilter;
  String? _selectedStatusFilter;

  // Track previous language to detect changes
  String? _previousLanguage;

  // Track if we've completed at least one load to avoid showing empty state prematurely
  bool _hasLoadedOnce = false;

  final OfflineFormsController _offlineForms = OfflineFormsController();
  bool _staleBannerDismissed = false;
  bool _wasOnline = true;
  OfflineProvider? _offlineProviderListenerRef;
  DashboardProvider? _dashboardProviderListenerRef;
  String _lastAssignmentSetSignature = '';

  /// Own controller so this list does not share the route's primary scroller
  /// with the other tabs in the page view. Those siblings can leave a non-zero
  /// offset, which is why the dashboard opened part-way down the list.
  final ScrollController _scrollController = ScrollController();
  bool _userDraggedDashboard = false;
  bool _correctingScroll = false;
  late final DateTime _scrollGuardUntil = DateTime.now().add(
    const Duration(seconds: 3),
  );

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
    final languageProvider = Provider.of<LanguageProvider>(
      context,
      listen: false,
    );
    _previousLanguage = languageProvider.currentLanguage;
    _scrollController.addListener(_onDashboardScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadData();
      _animationController.forward();
      if (!mounted) return;
      _offlineProviderListenerRef = Provider.of<OfflineProvider>(
        context,
        listen: false,
      );
      _offlineProviderListenerRef!.addListener(_onOfflineProviderChanged);
      _dashboardProviderListenerRef = Provider.of<DashboardProvider>(
        context,
        listen: false,
      );
      _dashboardProviderListenerRef!.addListener(_onDashboardProviderChanged);
      _wasOnline = _offlineProviderListenerRef!.isOnline;
      _offlineForms.addListener(_onOfflineFormsChanged);
      AssignmentOfflineBundleService.autoDownloadChanged.addListener(
        _onAutoDownloadChanged,
      );
    });
  }

  @override
  void dispose() {
    _offlineProviderListenerRef?.removeListener(_onOfflineProviderChanged);
    _dashboardProviderListenerRef?.removeListener(_onDashboardProviderChanged);
    _offlineForms.removeListener(_onOfflineFormsChanged);
    AssignmentOfflineBundleService.autoDownloadChanged.removeListener(
      _onAutoDownloadChanged,
    );
    _scrollController.removeListener(_onDashboardScroll);
    _scrollController.dispose();
    _animationController.dispose();
    super.dispose();
  }

  /// Off-screen layout in the tab page view can park this list mid-content
  /// before the user has touched it. Keep the header in view for the opening
  /// moments, then leave the offset alone.
  void _onDashboardScroll() {
    if (_userDraggedDashboard ||
        _correctingScroll ||
        DateTime.now().isAfter(_scrollGuardUntil) ||
        !_scrollController.hasClients ||
        _scrollController.offset == 0) {
      return;
    }
    _correctingScroll = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _correctingScroll = false;
      if (!mounted ||
          _userDraggedDashboard ||
          DateTime.now().isAfter(_scrollGuardUntil) ||
          !_scrollController.hasClients) {
        return;
      }
      if (_scrollController.offset != 0) {
        _scrollController.jumpTo(0);
      }
    });
  }

  void _onOfflineFormsChanged() {
    if (!mounted) return;
    if (!_offlineForms.hasOutdatedPackages) _staleBannerDismissed = false;
    setState(() {});
  }

  /// A connection that comes back is the moment to catch up on saved forms.
  void _onOfflineProviderChanged() {
    if (!mounted) return;
    final online = _offlineProviderListenerRef?.isOnline ?? true;
    final regained = online && !_wasOnline;
    _wasOnline = online;
    if (regained) unawaited(_reconcileOfflineForms(clearFailures: true));
  }

  void _onAutoDownloadChanged() {
    if (!mounted) return;
    unawaited(_reconcileOfflineForms(clearFailures: true));
  }

  /// The assignment list changes when another entity is selected. Offline state
  /// belongs to the template, so this only refreshes what is shown and adds the
  /// new entity's pages; it never downloads a saved template again.
  void _onDashboardProviderChanged() {
    if (!mounted) return;
    final provider = _dashboardProviderListenerRef;
    if (provider == null || provider.isLoading) return;
    final signature = [
      ...provider.currentAssignments.map((a) => a.id),
      -1,
      ...provider.pastAssignments.map((a) => a.id),
    ].join(',');
    if (signature == _lastAssignmentSetSignature) return;
    _lastAssignmentSetSignature = signature;
    unawaited(_reconcileOfflineForms());
  }

  OfflineFormsEnvironment _offlineEnvironment() {
    final offline = Provider.of<OfflineProvider>(context, listen: false);
    return OfflineFormsEnvironment(
      language: Provider.of<LanguageProvider>(
        context,
        listen: false,
      ).currentLanguage,
      submitBlockedMessage: AppLocalizations.of(
        context,
      )!.offlineSubmitRequiresConnection,
      online: offline.isOnline && !shouldDeferRemoteFetch,
    );
  }

  Future<void> _reconcileOfflineForms({bool clearFailures = false}) async {
    if (!mounted) return;
    final provider = Provider.of<DashboardProvider>(context, listen: false);
    final role = Provider.of<AuthProvider>(context, listen: false).user?.role;
    try {
      await _offlineForms.reconcile(
        all: [...provider.currentAssignments, ...provider.pastAssignments],
        eligible: provider.currentAssignments.where(
          (a) => _shouldShowEnterDataButton(role, a),
        ),
        env: _offlineEnvironment(),
        clearFailures: clearFailures,
      );
    } catch (e) {
      DebugLogger.logWarn('OFFLINE_BUNDLE', 'Reconcile failed: $e');
    }
  }

  Future<void> _loadData({bool forceRefresh = false}) async {
    final dashboardProvider = Provider.of<DashboardProvider>(
      context,
      listen: false,
    );
    final notificationProvider = Provider.of<NotificationProvider>(
      context,
      listen: false,
    );
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    final offline = Provider.of<OfflineProvider>(context, listen: false);

    // Offline or primary backoffice unreachable: avoid forced session checks and
    // dashboard API (retries/timeouts make pull-to-refresh feel stuck). Re-apply
    // last snapshot from disk only.
    if (offline.isOffline || shouldDeferRemoteFetch) {
      await authProvider.checkAuthStatus(forceRevalidate: false);
      await dashboardProvider.refreshFromDiskOnly(allowStale: true);
      await _offlineForms.refresh([
        ...dashboardProvider.currentAssignments,
        ...dashboardProvider.pastAssignments,
      ], language: _offlineEnvironment().language);
      if (mounted) {
        setState(() {
          _hasLoadedOnce = true;
        });
      }
      if (authProvider.isAuthenticated) {
        await dashboardProvider.loadEntities();
      }
      return;
    }

    // Force revalidation on dashboard load to ensure fresh session and role
    // This ensures we have a valid session before making API calls
    final isAuthenticated = await authProvider.checkAuthStatus(
      forceRevalidate: true,
    );

    // Load dashboard regardless of auth status (non-authenticated users can still view)
    // Force refresh if authenticated or if explicitly requested (e.g., language change)
    await dashboardProvider.loadDashboard(
      forceRefresh: isAuthenticated || forceRefresh,
    );

    await _offlineForms.prune(
      current: dashboardProvider.currentAssignments,
      past: dashboardProvider.pastAssignments,
    );

    // Mark that we've completed at least one load
    if (mounted) {
      setState(() {
        _hasLoadedOnce = true;
      });
    }

    if (mounted) {
      unawaited(_reconcileOfflineForms(clearFailures: forceRefresh));
    }

    // [checkAuthStatus(forceRevalidate: true)] already validated the session and
    // loaded the profile via AuthService — avoid a second [refreshUser] round-trip
    // (duplicate session check + duplicate profile fetch, noisy when the server
    // is down but Wi‑Fi still reports connected).
    if (isAuthenticated) {
      dashboardProvider.loadEntities();
      notificationProvider.refreshUnreadCount(authProvider: authProvider);
    }
  }

  Future<void> _openAssignmentForm(
    BuildContext context,
    Assignment assignment,
  ) async {
    final loc = AppLocalizations.of(context)!;
    final path = AppRoutes.formEntry(assignment.id);

    // Use saved assignment bundle when connectivity or backend reachability says
    // we should not rely on the live server (see [shouldDeferRemoteFetch]).
    if (shouldDeferRemoteFetch) {
      if (await AssignmentOfflineBundleService().hasOfflineForm(
        assignment.id,
      )) {
        if (!context.mounted) return;
        Navigator.of(context).pushNamed(
          AppRoutes.webview,
          arguments: WebViewScreenArgs(
            initialUrl: path,
            forceOfflineAssignmentBundle: true,
            offlineAssignmentId: assignment.id,
          ),
        );
        return;
      }
      if (!context.mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(loc.offlineFormNotDownloaded)));
      return;
    }

    if (!context.mounted) return;
    Navigator.of(context).pushNamed(AppRoutes.webview, arguments: path);
  }

  /// Saves the assignment's form for offline use (the template's shared files
  /// are only downloaded when the device does not have them yet).
  Future<void> _saveForOffline(Assignment assignment) async {
    final loc = AppLocalizations.of(context)!;
    final messenger = ScaffoldMessenger.of(context);
    final env = _offlineEnvironment();
    if (!env.online) {
      messenger.showSnackBar(
        SnackBar(content: Text(loc.offlineDownloadRequiresConnection)),
      );
      return;
    }
    final result = await _offlineForms.save(assignment, env);
    if (!mounted) return;
    if (result.ok) {
      messenger.showSnackBar(SnackBar(content: Text(loc.offlineFormSaved)));
      return;
    }
    final error = result.error;
    final detail = error is AssignmentOfflineBundleException
        ? error.message
        : error.runtimeType.toString();
    messenger.showSnackBar(
      SnackBar(
        content: Text('${loc.offlineFormSaveFailed}\n($detail)'),
        backgroundColor: Theme.of(context).colorScheme.error,
      ),
    );
  }

  Future<void> _removeOfflineBundle(Assignment assignment) async {
    final loc = AppLocalizations.of(context)!;
    final messenger = ScaffoldMessenger.of(context);
    final errorColor = Theme.of(context).colorScheme.error;
    try {
      await _offlineForms.remove(assignment);
      messenger.showSnackBar(SnackBar(content: Text(loc.offlineFormRemoved)));
    } catch (e) {
      messenger.showSnackBar(
        SnackBar(
          content: Text(loc.accessRequestsActionFailed),
          backgroundColor: errorColor,
        ),
      );
    }
  }

  String _formatOfflineBundleSavedAt(BuildContext context, DateTime date) {
    final locale = Localizations.localeOf(context);
    if (locale.languageCode == 'ar') {
      DateFormat.useNativeDigitsByDefaultFor('ar', false);
    }
    var formatted = DateFormat(
      'MMM d, y · HH:mm',
      locale.languageCode,
    ).format(date.toLocal());
    formatted = formatted
        .replaceAll('٠', '0')
        .replaceAll('١', '1')
        .replaceAll('٢', '2')
        .replaceAll('٣', '3')
        .replaceAll('٤', '4')
        .replaceAll('٥', '5')
        .replaceAll('٦', '6')
        .replaceAll('٧', '7')
        .replaceAll('٨', '8')
        .replaceAll('٩', '9');
    return formatted;
  }

  Future<void> _showOfflineBundleDetailsSheet(
    BuildContext context,
    Assignment assignment,
  ) async {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final status = _offlineForms.statusFor(assignment.id);
    final index = _offlineForms.index;
    final page = index.pages[assignment.id];
    final package = page == null ? null : index.packages[page.packageKey];
    final isStale = status.outdated;
    final canUpdateNow = _offlineEnvironment().online && isStale;

    final titleText =
        assignment.periodName != null && assignment.periodName!.isNotEmpty
        ? '${assignment.templateName ?? assignment.name} — ${assignment.periodName}'
        : (assignment.templateName ?? assignment.name);

    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        return Theme(
          data: GroupedSheetStyle.controlsTheme(sheetContext),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(
                IOSSpacing.lg,
                8,
                IOSSpacing.lg,
                IOSSpacing.lg,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    loc.offlineCopySheetTitle,
                    style: GroupedSheetStyle.title(sheetContext),
                  ),
                  SizedBox(height: IOSSpacing.smOf(sheetContext)),
                  Text(
                    titleText,
                    style: IOSTextStyle.subheadline(sheetContext).copyWith(
                      color: scheme.onSurface.withValues(alpha: 0.85),
                      height: 1.3,
                    ),
                  ),
                  if (page?.savedAtUtc != null) ...[
                    SizedBox(height: IOSSpacing.mdOf(sheetContext)),
                    Text(
                      loc.offlineCopySavedOnLabel,
                      style: IOSTextStyle.caption1(sheetContext).copyWith(
                        color: scheme.onSurface.withValues(alpha: 0.55),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    SizedBox(height: IOSSpacing.xsOf(sheetContext)),
                    Text(
                      _formatOfflineBundleSavedAt(
                        sheetContext,
                        page!.savedAtUtc!,
                      ),
                      style: IOSTextStyle.body(
                        sheetContext,
                      ).copyWith(fontWeight: FontWeight.w500),
                    ),
                  ],
                  SizedBox(height: IOSSpacing.mdOf(sheetContext)),
                  Text(
                    loc.offlineCopyFilesCached(package?.assetCount ?? 0),
                    style: IOSTextStyle.footnote(
                      sheetContext,
                    ).copyWith(color: scheme.onSurface.withValues(alpha: 0.7)),
                  ),
                  if (isStale) ...[
                    SizedBox(height: IOSSpacing.mdOf(sheetContext)),
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          Icons.warning_amber_rounded,
                          size: 20,
                          color: Color(AppConstants.warningColor),
                        ),
                        SizedBox(width: IOSSpacing.smOf(sheetContext)),
                        Expanded(
                          child: Text(
                            loc.offlineStaleBundleSheetNotice,
                            style: IOSTextStyle.subheadline(sheetContext)
                                .copyWith(
                                  color: scheme.onSurface.withValues(
                                    alpha: 0.88,
                                  ),
                                  height: 1.35,
                                ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  if (canUpdateNow) ...[
                    SizedBox(height: IOSSpacing.mdOf(sheetContext)),
                    FilledButton.icon(
                      onPressed: () async {
                        Navigator.of(sheetContext).pop();
                        await _saveForOffline(assignment);
                      },
                      icon: const Icon(Icons.sync_rounded, size: 20),
                      label: Text(loc.offlineStaleBundleUpdateNow),
                    ),
                  ],
                  SizedBox(height: IOSSpacing.lgOf(sheetContext)),
                  OutlinedButton.icon(
                    onPressed: () {
                      Navigator.of(sheetContext).pop();
                      unawaited(_removeOfflineBundle(assignment));
                    },
                    icon: Icon(
                      Icons.delete_outline_rounded,
                      color: scheme.error,
                    ),
                    label: Text(loc.removeOfflineCopy),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: scheme.error,
                      side: BorderSide(
                        color: scheme.error.withValues(alpha: 0.45),
                      ),
                      alignment: Alignment.center,
                      padding: const EdgeInsets.symmetric(vertical: 12),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
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

  Widget _buildOfflineStaleBundleBanner({
    required AppLocalizations loc,
    required OfflineProvider offline,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final online = offline.isOnline && !shouldDeferRemoteFetch;
    return Container(
      margin: const EdgeInsets.fromLTRB(
        IOSSpacing.lg,
        0,
        IOSSpacing.lg,
        IOSSpacing.md,
      ),
      padding: const EdgeInsets.all(IOSSpacing.md),
      decoration: BoxDecoration(
        color: const Color(AppConstants.warningColor).withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(
          IOSDimensions.borderRadiusLargeOf(context),
        ),
        border: Border.all(
          color: const Color(AppConstants.warningColor).withValues(alpha: 0.45),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.warning_amber_rounded,
            color: Color(AppConstants.warningColor),
            size: 22,
          ),
          SizedBox(width: IOSSpacing.mdOf(context)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  loc.offlineStaleBundleBannerTitle,
                  style: IOSTextStyle.subheadline(
                    context,
                  ).copyWith(fontWeight: FontWeight.w700, height: 1.25),
                ),
                SizedBox(height: IOSSpacing.xsOf(context)),
                Text(
                  online
                      ? loc.offlineStaleBundleBannerBodyOnline
                      : loc.offlineStaleBundleBannerBodyOffline,
                  style: IOSTextStyle.footnote(context).copyWith(
                    color: scheme.onSurface.withValues(alpha: 0.78),
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(minWidth: 32, minHeight: 32),
            icon: Icon(
              Icons.close_rounded,
              color: scheme.onSurface.withValues(alpha: 0.55),
              size: 20,
            ),
            onPressed: () {
              setState(() {
                _staleBannerDismissed = true;
              });
            },
          ),
        ],
      ),
    );
  }

  /// Open assignments as separate inset cards under a short section label.
  Widget _buildCurrentAssignmentsSection({
    required DashboardProvider provider,
    required AuthProvider authProvider,
    required OfflineProvider offlineProvider,
    required LanguageProvider languageProvider,
    required AppLocalizations localizations,
  }) {
    final assignments = provider.currentAssignments;
    if (assignments.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 22, 20, 10),
          child: DashboardSectionLabel(
            title: localizations.currentAssignments,
            count: assignments.length,
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16),
          child: Column(
            children: assignments.asMap().entries.map((entry) {
              final index = entry.key;
              final assignment = entry.value;
              final showEnter = _shouldShowEnterDataButton(
                authProvider.user?.role,
                assignment,
              );
              final offlineStatus = _offlineForms.statusFor(assignment.id);
              final hasBundle = offlineStatus.available;
              return AppFadeInUp(
                staggerIndex: index,
                child: DashboardGroupedAssignmentCard(
                  assignment: assignment,
                  onTap: () {
                    HapticFeedback.lightImpact();
                    unawaited(_openAssignmentForm(context, assignment));
                  },
                  showEnterDataButton: showEnter,
                  enterDataButtonText: localizations.enterData,
                  onEnterData: () {
                    HapticFeedback.mediumImpact();
                    unawaited(_openAssignmentForm(context, assignment));
                  },
                  onDownloadForOffline:
                      showEnter &&
                          offlineProvider.isOnline &&
                          !shouldDeferRemoteFetch
                      ? () => _saveForOffline(assignment)
                      : null,
                  onOfflineBundleDetails: hasBundle
                      ? () {
                          HapticFeedback.lightImpact();
                          unawaited(
                            _showOfflineBundleDetailsSheet(context, assignment),
                          );
                        }
                      : null,
                  hasOfflineFormSnapshot: hasBundle,
                  offlineBundleOutdated: offlineStatus.outdated,
                  isDownloadingOfflineForm: _offlineForms.isBusy(assignment.id),
                ),
              );
            }).toList(),
          ),
        ),
      ],
    );
  }

  // Past section: filters + single list (same structure as dashboard.html table, not status sub-groups)
  Widget _buildPastAssignmentsSection(DashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    // Get unique values for filters
    final periods =
        provider.pastAssignments
            .map((a) => a.periodName)
            .whereType<String>()
            .where((p) => p.isNotEmpty)
            .toSet()
            .toList()
          ..sort();

    final templates =
        provider.pastAssignments
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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          button: true,
          expanded: _pastAssignmentsExpanded,
          child: InkWell(
            onTap: () {
              HapticFeedback.selectionClick();
              setState(() {
                _pastAssignmentsExpanded = !_pastAssignmentsExpanded;
              });
            },
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
              child: Row(
                children: [
                  Expanded(
                    child: DashboardSectionLabel(
                      title: localizations.pastAssignments,
                      count: provider.pastAssignments.length,
                    ),
                  ),
                  AnimatedRotation(
                    turns: _pastAssignmentsExpanded ? 0.5 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: Icon(
                      Icons.expand_more_rounded,
                      size: 22,
                      color: theme.colorScheme.onSurface.withValues(
                        alpha: 0.48,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        if (_pastAssignmentsExpanded)
          ..._buildPastAssignmentsBody(
            localizations: localizations,
            periods: periods,
            templates: templates,
            statuses: statuses,
            filteredAssignments: filteredAssignments,
            sortedPast: sortedPast,
          ),
      ],
    );
  }

  List<Widget> _buildPastAssignmentsBody({
    required AppLocalizations localizations,
    required List<String> periods,
    required List<String> templates,
    required List<String> statuses,
    required List<Assignment> filteredAssignments,
    required List<Assignment> sortedPast,
  }) {
    return [
      // Filters Section - iOS style
      if (periods.isNotEmpty || templates.isNotEmpty || statuses.isNotEmpty)
        LayoutBuilder(
          builder: (context, constraints) {
            final canFitInline =
                constraints.maxWidth > 400; // Approximate breakpoint
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
                        GroupedSheetSectionLabel(localizations.filters),
                        SizedBox(width: IOSSpacing.mdOf(context)),
                        Expanded(
                          child: Wrap(
                            spacing: IOSSpacing.sm,
                            runSpacing: IOSSpacing.sm,
                            children: _buildFilterButtons(
                              localizations,
                              periods,
                              templates,
                              statuses,
                            ),
                          ),
                        ),
                      ],
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        GroupedSheetSectionLabel(localizations.filters),
                        SizedBox(height: IOSSpacing.mdOf(context) - 4),
                        Wrap(
                          spacing: IOSSpacing.sm,
                          runSpacing: IOSSpacing.sm,
                          children: _buildFilterButtons(
                            localizations,
                            periods,
                            templates,
                            statuses,
                          ),
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
                padding: const EdgeInsets.symmetric(horizontal: 16),
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
                      color: Theme.of(
                        context,
                      ).colorScheme.onSurface.withValues(alpha: 0.4),
                    ),
                    SizedBox(height: IOSSpacing.mdOf(context)),
                    Text(
                      localizations.noAssignmentsMatchFilters,
                      style: IOSTextStyle.subheadline(context).copyWith(
                        color: Theme.of(
                          context,
                        ).colorScheme.onSurface.withValues(alpha: 0.6),
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
    ];
  }

  List<Widget> _buildFilterButtons(
    AppLocalizations localizations,
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
        GroupedFilterChip(
          label: localizations.clear,
          icon: Icons.close_rounded,
          showChevron: false,
          onTap: () {
            setState(() {
              _selectedPeriodFilter = null;
              _selectedTemplateFilter = null;
              _selectedStatusFilter = null;
            });
          },
        ),
    ];
  }

  Widget _buildIOSFilterButton({
    required String label,
    required String? value,
    required VoidCallback onTap,
    bool isStatusFilter = false,
  }) {
    final localizations = AppLocalizations.of(context)!;
    final hasSelection = value != null;

    String displayText = label;
    if (hasSelection) {
      displayText = isStatusFilter
          ? localizations.localizeStatus(value)
          : value;
    }

    return GroupedFilterChip(
      label: displayText,
      selected: hasSelection,
      onTap: onTap,
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
    final allLabel = localizations.allYears.split(' ').first;
    showGroupedOptionPicker(
      context: context,
      title: title,
      closeTooltip: localizations.close,
      choices: [
        GroupedPickerChoice(
          label: allLabel,
          selected: selectedValue == null,
          onSelected: () => onSelected(null),
        ),
        ...options.map((option) {
          final displayText = isStatusFilter
              ? (option != null
                    ? localizations.localizeStatus(option)
                    : localizations.nA)
              : (option ?? localizations.nA);
          return GroupedPickerChoice(
            label: displayText,
            selected: option == selectedValue,
            onSelected: () => onSelected(option),
          );
        }),
      ],
    );
  }

  Widget _buildPastAssignmentCard(Assignment assignment, int index) {
    return AppFadeInUp(
      staggerIndex: index,
      child: DashboardGroupedAssignmentCard(
        assignment: assignment,
        onTap: () {
          HapticFeedback.lightImpact();
          unawaited(_openAssignmentForm(context, assignment));
        },
      ),
    );
  }

  void _showEntitySelector(BuildContext context, DashboardProvider provider) {
    EntitySelectorBottomSheet.show(context, provider);
  }

  Widget _buildPageHeader(
    DashboardProvider provider,
    AppLocalizations localizations,
  ) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final titleColor = isDark
        ? theme.colorScheme.onSurface
        : const Color(AppConstants.defaultNavy);
    final entity =
        provider.selectedEntity ??
        (provider.entities.isNotEmpty ? provider.entities.first : null);
    final hasMultipleEntities = provider.entities.length > 1;

    final titleStyle = IOSTextStyle.largeTitle(context).copyWith(
      fontWeight: FontWeight.w700,
      letterSpacing: -0.6,
      color: titleColor,
    );

    Widget? entityChip;
    if (entity != null) {
      entityChip = Material(
        color: isDark
            ? theme.colorScheme.surfaceContainerHigh
            : GroupedDashboardPalette.card,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(
            color: isDark
                ? theme.colorScheme.outlineVariant.withValues(alpha: 0.45)
                : GroupedDashboardPalette.hairline,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: hasMultipleEntities
              ? () {
                  HapticFeedback.lightImpact();
                  _showEntitySelector(context, provider);
                }
              : null,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.location_on_rounded,
                  size: 16,
                  color: titleColor.withValues(alpha: 0.7),
                ),
                const SizedBox(width: 6),
                Flexible(
                  child: Text(
                    entity.displayLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: IOSTextStyle.footnote(
                      context,
                    ).copyWith(fontWeight: FontWeight.w600, color: titleColor),
                  ),
                ),
                if (hasMultipleEntities) ...[
                  const SizedBox(width: 2),
                  Icon(
                    Icons.expand_more_rounded,
                    size: 18,
                    color: titleColor.withValues(alpha: 0.55),
                  ),
                ],
              ],
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 4),
      child: LayoutBuilder(
        builder: (context, constraints) {
          return Row(
            children: [
              ConstrainedBox(
                constraints: BoxConstraints(
                  maxWidth: constraints.maxWidth * 0.6,
                ),
                child: Text(
                  localizations.dashboard,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: titleStyle,
                ),
              ),
              if (entityChip != null) ...[
                const SizedBox(width: 12),
                Expanded(
                  child: Align(
                    alignment: AlignmentDirectional.centerEnd,
                    child: entityChip,
                  ),
                ),
              ],
            ],
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Consumer3<AuthProvider, LanguageProvider, OfflineProvider>(
      builder: (context, authProvider, languageProvider, offlineProvider, child) {
        final localizations = AppLocalizations.of(context)!;

        // Listen to language changes and reload dashboard data
        if (_previousLanguage != null &&
            _previousLanguage != languageProvider.currentLanguage) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            // Keep the previous snapshot until the translated refresh succeeds.
            // Deleting it here made downloaded assignments inaccessible when the
            // language changed while the device was offline.
            _previousLanguage = languageProvider.currentLanguage;
            // Reload data with force refresh to get new language content
            _loadData(forceRefresh: true);
          });
        }

        final canPop = Navigator.of(context).canPop();
        final groupedBackground = IOSColors.getGroupedBackground(context);
        return Scaffold(
          appBar: canPop ? const AppAppBar(title: '') : null,
          backgroundColor: groupedBackground,
          body: SafeArea(
            bottom: false,
            child: ColoredBox(
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
                    final bool shouldShowLoading =
                        provider.isLoading || !_hasLoadedOnce;

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
                      child: NotificationListener<ScrollNotification>(
                        onNotification: (notification) {
                          if (notification is ScrollStartNotification &&
                              notification.dragDetails != null) {
                            _userDraggedDashboard = true;
                          }
                          return false;
                        },
                        child: SingleChildScrollView(
                          controller: _scrollController,
                          primary: false,
                          physics: const AlwaysScrollableScrollPhysics(),
                          padding: EdgeInsets.zero,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              _buildPageHeader(provider, localizations),

                              if (_offlineForms.hasOutdatedPackages &&
                                  !_staleBannerDismissed)
                                _buildOfflineStaleBundleBanner(
                                  loc: localizations,
                                  offline: offlineProvider,
                                ),

                              // Open assignments (collapsible; title: "You have …")
                              if (provider.currentAssignments.isNotEmpty ||
                                  provider.pastAssignments.isNotEmpty)
                                _buildCurrentAssignmentsSection(
                                  provider: provider,
                                  authProvider: authProvider,
                                  offlineProvider: offlineProvider,
                                  languageProvider: languageProvider,
                                  localizations: localizations,
                                ),

                              // Past assignments (dashboard.html: collapsible + slicers + one list)
                              if (provider.pastAssignments.isNotEmpty) ...[
                                _buildPastAssignmentsSection(provider),
                              ],

                              if (provider.selectedEntity != null ||
                                  provider.entities.isNotEmpty)
                                Builder(
                                  builder: (context) {
                                    final entity =
                                        provider.selectedEntity ??
                                        provider.entities.first;
                                    return DashboardFocalPointsSection(
                                      entityLabel: entity.displayLabel,
                                      nsFocalPoints: provider.nsFocalPoints,
                                      orgFocalPoints: provider.orgFocalPoints,
                                    );
                                  },
                                ),

                              // Empty State - only show after we've loaded at least once
                              if (provider.currentAssignments.isEmpty &&
                                  provider.pastAssignments.isEmpty &&
                                  !provider.isLoading &&
                                  _hasLoadedOnce &&
                                  provider.error == null)
                                SizedBox(
                                  height:
                                      MediaQuery.of(context).size.height * 0.6,
                                  child: Center(
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 40,
                                      ),
                                      child: Column(
                                        mainAxisAlignment:
                                            MainAxisAlignment.center,
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
                                          SizedBox(
                                            height: IOSSpacing.xlOf(context),
                                          ),
                                          Text(
                                            localizations.noAssignmentsYet,
                                            style: IOSTextStyle.title2(context),
                                            textAlign: TextAlign.center,
                                          ),
                                          SizedBox(
                                            height: IOSSpacing.smOf(context),
                                          ),
                                          Text(
                                            localizations
                                                .newAssignmentsWillAppear,
                                            style:
                                                IOSTextStyle.subheadline(
                                                  context,
                                                ).copyWith(
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

                              // Clears the floating tab bar (padding.bottom is its
                              // height inside the tab shell).
                              SizedBox(
                                height:
                                    80 + MediaQuery.paddingOf(context).bottom,
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}
