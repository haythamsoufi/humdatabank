import 'dart:convert';
import 'package:flutter/material.dart';
import '../../services/storage_service.dart';
import '../../l10n/app_localizations.dart';
import '../../di/service_locator.dart';

// ---------------------------------------------------------------------------
// Tab identifiers
// ---------------------------------------------------------------------------

class TabIds {
  TabIds._();
  static const notifications = 'notifications';
  static const dashboard = 'dashboard';
  static const home = 'home';
  static const aiChat = 'ai_chat';
  static const admin = 'admin';
  static const analysis = 'analysis';
  static const settings = 'settings';
  static const resources = 'resources';
  static const indicators = 'indicators';
  static const unifiedPlanning = 'unified_planning';
}

// ---------------------------------------------------------------------------
// Tab metadata
// ---------------------------------------------------------------------------

class TabDefinition {
  final String id;
  final IconData icon;
  final IconData activeIcon;
  final String Function(AppLocalizations) getLabel;
  final bool isRequired;
  final bool showBadge;

  const TabDefinition({
    required this.id,
    required this.icon,
    required this.activeIcon,
    required this.getLabel,
    this.isRequired = false,
    this.showBadge = false,
  });
}

final List<TabDefinition> allTabDefinitions = [
  TabDefinition(
    id: TabIds.notifications,
    icon: Icons.notifications_outlined,
    activeIcon: Icons.notifications,
    getLabel: (l) => l.notifications,
    showBadge: true,
  ),
  TabDefinition(
    id: TabIds.dashboard,
    icon: Icons.dashboard_outlined,
    activeIcon: Icons.dashboard,
    getLabel: (l) => l.dashboard,
  ),
  TabDefinition(
    id: TabIds.home,
    icon: Icons.home_outlined,
    activeIcon: Icons.home,
    getLabel: (l) => l.home,
    isRequired: true,
  ),
  TabDefinition(
    id: TabIds.aiChat,
    icon: Icons.smart_toy_outlined,
    activeIcon: Icons.smart_toy,
    getLabel: (l) => l.chatbot,
  ),
  TabDefinition(
    id: TabIds.admin,
    icon: Icons.admin_panel_settings_outlined,
    activeIcon: Icons.admin_panel_settings,
    getLabel: (l) => l.admin,
  ),
  TabDefinition(
    id: TabIds.analysis,
    icon: Icons.analytics_outlined,
    activeIcon: Icons.analytics,
    getLabel: (l) => l.analysis,
  ),
  TabDefinition(
    id: TabIds.settings,
    icon: Icons.settings_outlined,
    activeIcon: Icons.settings,
    getLabel: (l) => l.settings,
  ),
  TabDefinition(
    id: TabIds.resources,
    icon: Icons.folder_outlined,
    activeIcon: Icons.folder,
    getLabel: (l) => l.resources,
  ),
  TabDefinition(
    id: TabIds.indicators,
    icon: Icons.library_books_outlined,
    activeIcon: Icons.library_books,
    getLabel: (l) => l.indicators,
  ),
  TabDefinition(
    id: TabIds.unifiedPlanning,
    icon: Icons.description_outlined,
    activeIcon: Icons.description,
    getLabel: (l) => l.resourcesUnifiedPlanningSectionTitle,
  ),
];

final Map<String, TabDefinition> tabDefinitionMap = {
  for (final d in allTabDefinitions) d.id: d,
};

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

class TabCustomizationProvider extends ChangeNotifier {
  static const _prefsKeyPrefix = 'tab_customization_';
  static const int minVisibleTabs = 2;

  final StorageService _storage = sl<StorageService>();
  final Map<String, List<String>> _customOrder = {};
  final Map<String, Set<String>> _hiddenTabs = {};
  bool _loaded = false;

  // ── Role key ──────────────────────────────────────────────────────────────

  static String _roleKey({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
  }) {
    if (isAdmin) return 'admin';
    if (isAuthenticated && isFocalPoint) return 'focal';
    if (isAuthenticated) return 'auth';
    return 'guest';
  }

  // ── Default / available tab sets per role ─────────────────────────────────

  static List<String> defaultTabIdsForRole({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
    required bool chatbotEnabled,
  }) {
    if (isAdmin) {
      return [
        TabIds.notifications,
        TabIds.dashboard,
        TabIds.home,
        TabIds.unifiedPlanning,
        if (chatbotEnabled) TabIds.aiChat,
        TabIds.admin,
      ];
    }
    if (isAuthenticated && isFocalPoint) {
      return [
        TabIds.notifications,
        TabIds.dashboard,
        TabIds.home,
        TabIds.unifiedPlanning,
        if (chatbotEnabled) TabIds.aiChat,
        TabIds.analysis,
        TabIds.settings,
      ];
    }
    if (isAuthenticated) {
      return [
        TabIds.resources,
        TabIds.dashboard,
        TabIds.home,
        TabIds.unifiedPlanning,
        if (chatbotEnabled) TabIds.aiChat,
        TabIds.analysis,
        TabIds.settings,
      ];
    }
    return [
      TabIds.resources,
      TabIds.indicators,
      TabIds.home,
      TabIds.unifiedPlanning,
      if (chatbotEnabled) TabIds.aiChat,
      TabIds.analysis,
      TabIds.settings,
    ];
  }

  /// Tab IDs that can never be hidden for this role, regardless of user
  /// customisation.  These are surfaced in the dialog as "always shown".
  static Set<String> requiredTabIdsForRole({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
  }) {
    if (isAdmin) return {TabIds.admin};
    return {};
  }

  /// Superset of all tab IDs the role is allowed to enable.
  static Set<String> availableTabIdsForRole({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
    required bool chatbotEnabled,
  }) {
    final ids = <String>{TabIds.home};
    if (isAdmin) {
      ids.addAll([
        TabIds.notifications, TabIds.dashboard, TabIds.admin,
        TabIds.analysis, TabIds.resources, TabIds.settings,
        TabIds.unifiedPlanning,
      ]);
    } else if (isAuthenticated) {
      ids.addAll([
        TabIds.notifications, TabIds.dashboard, TabIds.resources,
        TabIds.analysis, TabIds.settings, TabIds.indicators,
        TabIds.unifiedPlanning,
      ]);
    } else {
      ids.addAll([
        TabIds.resources, TabIds.indicators,
        TabIds.analysis, TabIds.settings, TabIds.unifiedPlanning,
      ]);
    }
    if (chatbotEnabled) ids.add(TabIds.aiChat);
    return ids;
  }

  // ── Persistence ───────────────────────────────────────────────────────────

  Future<void> loadPreferences() async {
    if (_loaded) return;
    for (final rk in ['admin', 'focal', 'auth', 'guest']) {
      final raw = await _storage.getString('$_prefsKeyPrefix$rk');
      if (raw == null) continue;
      try {
        final data = jsonDecode(raw) as Map<String, dynamic>;
        _customOrder[rk] = List<String>.from(data['order'] ?? []);
        _hiddenTabs[rk] = Set<String>.from(data['hidden'] ?? []);
      } catch (_) {
        // Corrupted data — will fall back to defaults.
      }
    }
    _loaded = true;
  }

  // ── Queries ───────────────────────────────────────────────────────────────

  /// Ordered visible tabs for the main navigation screen.
  List<TabDefinition> getVisibleTabs({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
    required bool chatbotEnabled,
  }) {
    final rk = _roleKey(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
    );
    final available = availableTabIdsForRole(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
      chatbotEnabled: chatbotEnabled,
    );

    final custom = _customOrder[rk];
    final hidden = _hiddenTabs[rk] ?? {};
    final roleRequired = requiredTabIdsForRole(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
    );

    List<String> ordered;
    if (custom != null && custom.isNotEmpty) {
      ordered = custom.where(available.contains).toList();
      // Append newly-available tabs the user hasn't seen yet.
      for (final id in defaultTabIdsForRole(
        isAdmin: isAdmin,
        isAuthenticated: isAuthenticated,
        isFocalPoint: isFocalPoint,
        chatbotEnabled: chatbotEnabled,
      )) {
        if (!ordered.contains(id)) ordered.add(id);
      }
    } else {
      ordered = defaultTabIdsForRole(
        isAdmin: isAdmin,
        isAuthenticated: isAuthenticated,
        isFocalPoint: isFocalPoint,
        chatbotEnabled: chatbotEnabled,
      );
    }

    // Ensure role-required tabs are always present even if missing from the
    // saved custom order (e.g. added after the user last customised).
    for (final id in roleRequired) {
      if (!ordered.contains(id) && tabDefinitionMap.containsKey(id)) {
        ordered.add(id);
      }
    }

    ordered = ordered.where((id) {
      final def = tabDefinitionMap[id];
      if (def == null) return false;
      if (def.isRequired) return true;
      // Role-critical tabs (e.g. Admin for system_manager/admin) are never
      // removed by the hidden-set, even if the user previously toggled them off.
      if (roleRequired.contains(id)) return true;
      return !hidden.contains(id);
    }).toList();

    if (!ordered.contains(TabIds.home)) {
      ordered.insert(0, TabIds.home);
    }

    return ordered
        .where((id) => tabDefinitionMap.containsKey(id))
        .map((id) => tabDefinitionMap[id]!)
        .toList();
  }

  /// All available tabs with current visibility — used by the customization
  /// dialog to let the user toggle and reorder.
  List<({TabDefinition tab, bool visible})> getTabsForDialog({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
    required bool chatbotEnabled,
  }) {
    final rk = _roleKey(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
    );
    final available = availableTabIdsForRole(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
      chatbotEnabled: chatbotEnabled,
    );

    final custom = _customOrder[rk];
    final hidden = _hiddenTabs[rk] ?? {};

    List<String> ordered;
    if (custom != null && custom.isNotEmpty) {
      ordered = custom.where(available.contains).toList();
      for (final id in available) {
        if (!ordered.contains(id)) ordered.add(id);
      }
    } else {
      ordered = defaultTabIdsForRole(
        isAdmin: isAdmin,
        isAuthenticated: isAuthenticated,
        isFocalPoint: isFocalPoint,
        chatbotEnabled: chatbotEnabled,
      );
      for (final id in available) {
        if (!ordered.contains(id)) ordered.add(id);
      }
    }

    return ordered
        .where((id) => tabDefinitionMap.containsKey(id))
        .map((id) {
      final def = tabDefinitionMap[id]!;
      return (tab: def, visible: def.isRequired || !hidden.contains(id));
    }).toList();
  }

  /// Index of [tabId] within the current visible tabs, or -1 if absent.
  int indexOfTab(
    String tabId, {
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
    required bool chatbotEnabled,
  }) {
    final tabs = getVisibleTabs(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
      chatbotEnabled: chatbotEnabled,
    );
    return tabs.indexWhere((t) => t.id == tabId);
  }

  // ── Mutations ─────────────────────────────────────────────────────────────

  Future<void> saveCustomization({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
    required List<String> orderedIds,
    required Set<String> hiddenIds,
  }) async {
    final rk = _roleKey(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
    );

    _customOrder[rk] = List.from(orderedIds);
    _hiddenTabs[rk] = Set.from(hiddenIds);

    await _storage.setString(
      '$_prefsKeyPrefix$rk',
      jsonEncode({'order': orderedIds, 'hidden': hiddenIds.toList()}),
    );
    notifyListeners();
  }

  Future<void> resetToDefaults({
    required bool isAdmin,
    required bool isAuthenticated,
    required bool isFocalPoint,
  }) async {
    final rk = _roleKey(
      isAdmin: isAdmin,
      isAuthenticated: isAuthenticated,
      isFocalPoint: isFocalPoint,
    );
    _customOrder.remove(rk);
    _hiddenTabs.remove(rk);
    await _storage.remove('$_prefsKeyPrefix$rk');
    notifyListeners();
  }
}
