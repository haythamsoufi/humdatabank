import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/notification_provider.dart';
import '../providers/shared/auth_provider.dart';
import '../providers/shared/tab_customization_provider.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/navigation_helper.dart';
import '../l10n/app_localizations.dart';
import 'tab_customization_dialog.dart';

class AppBottomNavigationBar extends StatelessWidget {
  /// Pass as [currentIndex] when no tab should appear selected.
  static const int noTabSelected = -1;

  /// Legacy: page index for Settings in an older 5-tab guest layout.
  /// Prefer [TabCustomizationProvider.indexOfTab] with [TabIds.settings].
  @Deprecated('Resolve settings tab index via TabCustomizationProvider')
  static const int settingsTabIndex = 5;

  /// Bottom bar index for the AI tab when [chatbotEnabled] is true
  /// (after home + unified planning in the default layout).
  static const int aiChatNavIndex = 4;

  /// Bottom bar slot for the Admin/Analysis tab (shifts right when AI is shown).
  static int adminTabNavIndex({required bool chatbotEnabled}) =>
      chatbotEnabled ? 5 : 4;

  final int currentIndex;
  final Function(int)? onTap;
  final bool? isFocalPoint;
  final bool useDefaultNavigation;

  /// When `null`, uses [AuthProvider] `user.chatbotEnabled`.
  final bool? chatbotEnabled;

  /// When non-null the bar renders exactly these tabs (customization-aware).
  /// Pass `null` to fall back to the built-in role-based layout.
  final List<TabDefinition>? visibleTabs;

  /// When `true`, long-pressing the bar opens the tab customization dialog.
  final bool enableCustomization;

  /// When non-null, used as the bar background instead of [Theme] surface
  /// (e.g. translucent black over a full-screen PDF).
  final Color? backgroundColor;

  /// Light icon colours for dark translucent bars ([backgroundColor] with low opacity).
  final bool lightForegroundOnBar;

  const AppBottomNavigationBar({
    super.key,
    required this.currentIndex,
    this.onTap,
    this.isFocalPoint,
    this.useDefaultNavigation = true,
    this.chatbotEnabled,
    this.visibleTabs,
    this.enableCustomization = false,
    this.backgroundColor,
    this.lightForegroundOnBar = false,
  });

  bool _effectiveChatbot(BuildContext context) {
    if (chatbotEnabled != null) return chatbotEnabled!;
    // Use listen: false — consistent with _isAdmin / _isAuthenticated / _isFocalPoint.
    // Auth-state changes trigger parent rebuilds (e.g. Consumer in MainNavigationScreen)
    // which reconstruct this widget with updated values.
    return Provider.of<AuthProvider>(context, listen: false).user?.chatbotEnabled ?? false;
  }

  void _handleTap(BuildContext context, int index) {
    if (onTap != null) {
      onTap!(index);
    } else if (useDefaultNavigation) {
      // Nav index == PageView page index (1:1 since AI Chat is a real page).
      NavigationHelper.navigateToMainTab(context, index);
    }
  }

  bool _isAdmin(BuildContext context) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.user?.isAdmin ?? false;
  }

  bool _isAuthenticated(BuildContext context) {
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.isAuthenticated;
  }

  bool _isFocalPoint(BuildContext context) {
    if (isFocalPoint != null) return isFocalPoint!;
    final authProvider = Provider.of<AuthProvider>(context, listen: false);
    return authProvider.user?.isFocalPoint ?? false;
  }

  @override
  Widget build(BuildContext context) {
    // ── Customized path ─────────────────────────────────────────────────────
    if (visibleTabs != null && visibleTabs!.isNotEmpty) {
      return _buildCustomized(context, visibleTabs!);
    }
    // ── Legacy / hardcoded path (admin sub-screens, etc.) ───────────────────
    return _buildLegacy(context);
  }

  // =========================================================================
  // Customized layout — driven by [visibleTabs]
  // =========================================================================

  Widget _buildCustomized(BuildContext context, List<TabDefinition> tabs) {
    final int itemCount = tabs.length;
    final int selectedTabIndex = currentIndex < 0
        ? -1
        : (currentIndex >= itemCount ? itemCount - 1 : currentIndex);

    final l10n = AppLocalizations.of(context)!;

    return _barShell(
      context: context,
      enableCustomization: enableCustomization,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          for (int i = 0; i < tabs.length; i++)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: i,
                selectedTabIndex: selectedTabIndex,
                icon: tabs[i].icon,
                activeIcon: tabs[i].activeIcon,
                label: tabs[i].getLabel(l10n),
                showBadge: tabs[i].showBadge,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, i),
              ),
            ),
        ],
      ),
    );
  }

  // =========================================================================
  // Legacy layout — hardcoded per role (unchanged logic)
  // =========================================================================

  Widget _buildLegacy(BuildContext context) {
    final isAdmin = _isAdmin(context);
    final isAuthenticated = _isAuthenticated(context);
    final isFocalPoint = _isFocalPoint(context);
    final c = _effectiveChatbot(context);

    // When chatbot is enabled, indices from the AI slot onward are +1 vs no-AI layout.
    final int shiftedIdx = c ? 5 : 4;
    final int settingsIdx = c ? 6 : 5;

    // Tab layout (visual left→right, indices match PageView pages):
    // Admin:          … Home(2) Unified planning(3) [AI(4)] Admin(4/5)
    // Focal/Auth/Guest: … Home(2) Unified planning(3) [AI(4)] Analysis(4/5) Settings(5/6)
    final int itemCount = (isAdmin ? 5 : 6) + (c ? 1 : 0);

    // Negative currentIndex → no tab highlighted (e.g. login overlay).
    // Do not coerce to 0 — that would incorrectly highlight the first tab.
    final int selectedTabIndex = currentIndex < 0
        ? -1
        : (currentIndex >= itemCount ? itemCount - 1 : currentIndex);

    final l10n = AppLocalizations.of(context)!;

    // The AI tab is identical in both admin and non-admin layouts — defined once here.
    Widget aiTab() => Flexible(
          flex: 1,
          child: _buildNavItem(
            context: context,
            index: aiChatNavIndex,
            selectedTabIndex: selectedTabIndex,
            icon: Icons.auto_awesome_outlined,
            activeIcon: Icons.auto_awesome,
            label: l10n.chatbot,
            showBadge: false,
            lightForegroundOnBar: lightForegroundOnBar,
            onTap: () => _handleTap(context, aiChatNavIndex),
          ),
        );

    return _barShell(
      context: context,
      enableCustomization: enableCustomization,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          if (isAdmin) ...[
            // Notifications (index 0) — admin only
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 0,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.notifications_outlined,
                activeIcon: Icons.notifications,
                label: l10n.notifications,
                showBadge: true,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, 0),
              ),
            ),
            // Dashboard (index 1)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 1,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.grid_view_outlined,
                activeIcon: Icons.grid_view,
                label: l10n.dashboard,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, 1),
              ),
            ),
            // Home (index 2)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 2,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.home_outlined,
                activeIcon: Icons.home_rounded,
                label: l10n.home,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, 2),
              ),
            ),
            // Unified planning documents (index 3)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 3,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.assignment_outlined,
                activeIcon: Icons.assignment,
                label: l10n.resourcesUnifiedPlanningSectionTitle,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, 3),
              ),
            ),
            if (c) aiTab(),
            // Admin hub (index shifts when AI is shown)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: shiftedIdx,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.shield_outlined,
                activeIcon: Icons.shield,
                label: l10n.admin,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, shiftedIdx),
              ),
            ),
          ] else ...[
            // Focal points see Notifications; other authenticated users see Resources.
            if (isAuthenticated)
              Flexible(
                flex: 1,
                child: _buildNavItem(
                  context: context,
                  index: 0,
                  selectedTabIndex: selectedTabIndex,
                  icon: isFocalPoint
                      ? Icons.notifications_outlined
                      : Icons.folder_open_outlined,
                  activeIcon: isFocalPoint
                      ? Icons.notifications
                      : Icons.folder_open,
                  label: isFocalPoint ? l10n.notifications : l10n.resources,
                  showBadge: isFocalPoint,
                  lightForegroundOnBar: lightForegroundOnBar,
                  onTap: () => _handleTap(context, 0),
                ),
              ),
            // Resources (index 0) — only for non-authenticated users.
            // Must be rendered before Indicators so visual order matches page order.
            if (!isAuthenticated)
              Flexible(
                flex: 1,
                child: _buildNavItem(
                  context: context,
                  index: 0,
                  selectedTabIndex: selectedTabIndex,
                  icon: Icons.folder_open_outlined,
                  activeIcon: Icons.folder_open,
                  label: l10n.resources,
                  showBadge: false,
                  lightForegroundOnBar: lightForegroundOnBar,
                  onTap: () => _handleTap(context, 0),
                ),
              ),
            // Indicators (index 1) — only for non-authenticated users.
            if (!isAuthenticated)
              Flexible(
                flex: 1,
                child: _buildNavItem(
                  context: context,
                  index: 1,
                  selectedTabIndex: selectedTabIndex,
                  icon: Icons.menu_book_outlined,
                  activeIcon: Icons.menu_book,
                  label: l10n.indicators,
                  showBadge: false,
                  lightForegroundOnBar: lightForegroundOnBar,
                  onTap: () => _handleTap(context, 1),
                ),
              ),
            // Dashboard — centre slot for authenticated non-admin users.
            if (isAuthenticated)
              Flexible(
                flex: 1,
                child: _buildNavItem(
                  context: context,
                  index: 1,
                  selectedTabIndex: selectedTabIndex,
                  icon: Icons.grid_view_outlined,
                  activeIcon: Icons.grid_view,
                  label: l10n.dashboard,
                  showBadge: false,
                  lightForegroundOnBar: lightForegroundOnBar,
                  onTap: () => _handleTap(context, 1),
                ),
              ),
            // Home (index 2)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 2,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.home_outlined,
                activeIcon: Icons.home_rounded,
                label: l10n.home,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, 2),
              ),
            ),
            // Unified planning documents (index 3)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: 3,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.assignment_outlined,
                activeIcon: Icons.assignment,
                label: l10n.resourcesUnifiedPlanningSectionTitle,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, 3),
              ),
            ),
            if (c) aiTab(),
            // Disaggregation Analysis (index shifts when AI is shown)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: shiftedIdx,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.insights_outlined,
                activeIcon: Icons.insights,
                label: l10n.analysis,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, shiftedIdx),
              ),
            ),
            // Settings (index shifts when AI is shown)
            Flexible(
              flex: 1,
              child: _buildNavItem(
                context: context,
                index: settingsIdx,
                selectedTabIndex: selectedTabIndex,
                icon: Icons.settings_outlined,
                activeIcon: Icons.settings,
                label: l10n.settings,
                showBadge: false,
                lightForegroundOnBar: lightForegroundOnBar,
                onTap: () => _handleTap(context, settingsIdx),
              ),
            ),
          ],
        ],
      ),
    );
  }

  // =========================================================================
  // Shared shell (border, safe area, optional long-press)
  // =========================================================================

  Widget _barShell({
    required BuildContext context,
    required bool enableCustomization,
    required Widget child,
  }) {
    final barBg = backgroundColor ?? context.surfaceColor;
    final topBorderColor = backgroundColor != null
        ? Colors.white.withValues(alpha: 0.14)
        : context.borderColor;

    Widget bar = Container(
      decoration: BoxDecoration(
        color: barBg,
        border: Border(
          top: BorderSide(
            color: topBorderColor,
            width: 0.5,
          ),
        ),
      ),
      child: SafeArea(
        top: false,
        child: SizedBox(
          height: 52,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(6, 0, 6, 4),
            child: child,
          ),
        ),
      ),
    );

    if (enableCustomization) {
      bar = GestureDetector(
        onLongPress: () => TabCustomizationDialog.show(context),
        child: bar,
      );
    }

    return bar;
  }

  // =========================================================================
  // Individual nav item
  // =========================================================================

  Widget _buildNavItem({
    required BuildContext context,
    required int index,
    required int selectedTabIndex,
    required IconData icon,
    required IconData activeIcon,
    required String label,
    /// When true, wraps the icon in a [Consumer<NotificationProvider>] badge.
    required bool showBadge,
    required bool lightForegroundOnBar,
    required VoidCallback onTap,
  }) {
    final isSelected = selectedTabIndex >= 0 && selectedTabIndex == index;
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final primary = cs.primary;
    final ifrcRed = Color(AppConstants.ifrcRed);

    final Color iconFg;
    final Color stripeColor;
    if (lightForegroundOnBar) {
      stripeColor = ifrcRed;
      iconFg = isSelected
          ? Colors.white
          : Colors.white.withValues(alpha: 0.62);
    } else if (isSelected) {
      stripeColor = ifrcRed;
      iconFg = context.isDarkTheme
          ? Color.alphaBlend(Colors.white.withValues(alpha: 0.22), primary)
          : primary;
    } else {
      stripeColor = Colors.transparent;
      iconFg = context.iconColor
          .withValues(alpha: context.isDarkTheme ? 0.72 : 0.55);
    }

    Widget iconChild;
    if (showBadge) {
      iconChild = Consumer<NotificationProvider>(
        builder: (context, provider, child) {
          return Stack(
            clipBehavior: Clip.none,
            alignment: Alignment.center,
            children: [
              Icon(
                isSelected ? activeIcon : icon,
                size: 24,
                color: iconFg,
              ),
              if (provider.unreadCount > 0)
                Positioned(
                  right: -6,
                  top: -6,
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 4, vertical: 2),
                    decoration: BoxDecoration(
                      color: Color(AppConstants.ifrcRed),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    constraints: const BoxConstraints(
                      minWidth: 16,
                      minHeight: 16,
                    ),
                    child: Center(
                      child: Text(
                        provider.unreadCount > 9
                            ? '9+'
                            : '${provider.unreadCount}',
                        style: TextStyle(
                          color: theme.colorScheme.onPrimary,
                          fontWeight: FontWeight.bold,
                          fontSize: 10,
                        ),
                      ),
                    ),
                  ),
                ),
            ],
          );
        },
      );
    } else {
      iconChild = Icon(
        isSelected ? activeIcon : icon,
        size: 24,
        color: iconFg,
      );
    }

    return Semantics(
      label: label,
      button: true,
      selected: isSelected,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          splashColor: context.isDarkTheme && isSelected
              ? Colors.white.withValues(alpha: 0.18)
              : primary.withValues(alpha: 0.12),
          highlightColor: context.isDarkTheme && isSelected
              ? Colors.white.withValues(alpha: 0.1)
              : primary.withValues(alpha: 0.06),
          child: SizedBox.expand(
            child: Column(
              children: [
                AnimatedContainer(
                  duration: AppConstants.animationFast,
                  curve: Curves.easeOutCubic,
                  height: 3,
                  margin: EdgeInsets.symmetric(horizontal: isSelected ? 10 : 0),
                  decoration: BoxDecoration(
                    color: isSelected ? stripeColor : Colors.transparent,
                    borderRadius: const BorderRadius.vertical(
                      bottom: Radius.circular(1.5),
                    ),
                  ),
                ),
                Expanded(
                  child: Center(
                    child: AnimatedScale(
                      scale: isSelected ? 1.0 : 0.94,
                      duration: AppConstants.animationFast,
                      curve: Curves.easeOutCubic,
                      child: iconChild,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
