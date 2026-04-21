import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/tab_customization_provider.dart';
import '../providers/shared/auth_provider.dart';
import '../l10n/app_localizations.dart';
import '../utils/theme_extensions.dart';

class _EditableTab {
  final TabDefinition def;
  bool visible;
  _EditableTab(this.def, this.visible);
}

/// Modal bottom sheet for choosing which bottom-nav tabs to show and their
/// display order.  Open it with [TabCustomizationDialog.show].
class TabCustomizationDialog extends StatefulWidget {
  const TabCustomizationDialog({super.key});

  /// Opens the customization sheet.  Returns `true` when the user saved
  /// changes, `null` / `false` otherwise.
  static Future<bool?> show(BuildContext context) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      backgroundColor: Colors.transparent,
      builder: (_) => ChangeNotifierProvider.value(
        value: Provider.of<TabCustomizationProvider>(context, listen: false),
        child: const TabCustomizationDialog(),
      ),
    );
  }

  @override
  State<TabCustomizationDialog> createState() =>
      _TabCustomizationDialogState();
}

class _TabCustomizationDialogState extends State<TabCustomizationDialog> {
  late List<_EditableTab> _tabs;
  bool _initialized = false;

  late bool _isAdmin;
  late bool _isAuthenticated;
  late bool _isFocalPoint;
  late bool _chatbotEnabled;
  late Set<String> _roleRequiredTabs;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_initialized) return;
    _initTabs();
    _initialized = true;
  }

  void _initTabs() {
    final auth = Provider.of<AuthProvider>(context, listen: false);
    final user = auth.user;
    _isAdmin = user?.isAdmin ?? false;
    _isAuthenticated = auth.isAuthenticated;
    _isFocalPoint = user?.isFocalPoint ?? false;
    _chatbotEnabled = user?.chatbotEnabled ?? false;

    _roleRequiredTabs = TabCustomizationProvider.requiredTabIdsForRole(
      isAdmin: _isAdmin,
      isAuthenticated: _isAuthenticated,
      isFocalPoint: _isFocalPoint,
    );

    final provider =
        Provider.of<TabCustomizationProvider>(context, listen: false);
    final items = provider.getTabsForDialog(
      isAdmin: _isAdmin,
      isAuthenticated: _isAuthenticated,
      isFocalPoint: _isFocalPoint,
      chatbotEnabled: _chatbotEnabled,
    );
    _tabs = items.map((e) => _EditableTab(e.tab, e.visible)).toList();
  }

  int get _visibleCount => _tabs.where((t) => t.visible).length;

  void _onReorder(int oldIndex, int newIndex) {
    setState(() {
      if (newIndex > oldIndex) newIndex--;
      final item = _tabs.removeAt(oldIndex);
      _tabs.insert(newIndex, item);
    });
  }

  void _toggle(_EditableTab tab) {
    if (tab.def.isRequired) return;
    if (_roleRequiredTabs.contains(tab.def.id)) return;
    if (tab.visible &&
        _visibleCount <= TabCustomizationProvider.minVisibleTabs) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content:
              Text(AppLocalizations.of(context)!.minimumTabsWarning),
          duration: const Duration(seconds: 2),
        ),
      );
      return;
    }
    setState(() => tab.visible = !tab.visible);
  }

  void _resetToDefaults() {
    final defaults = TabCustomizationProvider.defaultTabIdsForRole(
      isAdmin: _isAdmin,
      isAuthenticated: _isAuthenticated,
      isFocalPoint: _isFocalPoint,
      chatbotEnabled: _chatbotEnabled,
    );
    setState(() {
      _tabs.sort((a, b) {
        final ai = defaults.indexOf(a.def.id);
        final bi = defaults.indexOf(b.def.id);
        return (ai < 0 ? 999 : ai).compareTo(bi < 0 ? 999 : bi);
      });
      for (final t in _tabs) {
        t.visible = defaults.contains(t.def.id);
      }
    });
  }

  Future<void> _save() async {
    final provider =
        Provider.of<TabCustomizationProvider>(context, listen: false);
    await provider.saveCustomization(
      isAdmin: _isAdmin,
      isAuthenticated: _isAuthenticated,
      isFocalPoint: _isFocalPoint,
      orderedIds: _tabs.map((t) => t.def.id).toList(),
      hiddenIds:
          _tabs.where((t) => !t.visible).map((t) => t.def.id).toSet(),
    );
    if (mounted) Navigator.of(context).pop(true);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Container(
      decoration: BoxDecoration(
        color: context.surfaceColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
      ),
      child: DraggableScrollableSheet(
        initialChildSize: 0.6,
        minChildSize: 0.4,
        maxChildSize: 0.85,
        expand: false,
        builder: (context, scrollController) {
          return Column(
            children: [
              // ── Drag handle ───────────────────────────────────────────
              Center(
                child: Container(
                  margin: const EdgeInsets.only(top: 12),
                  width: 36,
                  height: 4,
                  decoration: BoxDecoration(
                    color: context.borderColor,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),

              // ── Header ────────────────────────────────────────────────
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 16, 8, 8),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            l10n.customizeTabs,
                            style: theme.textTheme.titleLarge
                                ?.copyWith(fontWeight: FontWeight.w600),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            l10n.customizeTabsDescription,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: context.textSecondaryColor,
                            ),
                          ),
                        ],
                      ),
                    ),
                    TextButton.icon(
                      onPressed: _resetToDefaults,
                      icon: const Icon(Icons.restart_alt, size: 18),
                      label: Text(l10n.resetToDefault),
                    ),
                  ],
                ),
              ),
              Divider(height: 1, color: context.borderColor),

              // ── Reorderable tab list ──────────────────────────────────
              Expanded(
                child: ReorderableListView.builder(
                  scrollController: scrollController,
                  buildDefaultDragHandles: false,
                  itemCount: _tabs.length,
                  onReorder: _onReorder,
                  proxyDecorator: (child, _, _) {
                    return Material(
                      elevation: 4,
                      color: context.surfaceColor,
                      borderRadius: BorderRadius.circular(8),
                      child: child,
                    );
                  },
                  itemBuilder: (context, index) {
                    final tab = _tabs[index];
                    final label = tab.def.getLabel(l10n);
                    final isEffectivelyRequired = tab.def.isRequired ||
                        _roleRequiredTabs.contains(tab.def.id);

                    return Material(
                      key: ValueKey(tab.def.id),
                      color: Colors.transparent,
                      child: ListTile(
                        leading: Icon(
                          tab.visible
                              ? tab.def.activeIcon
                              : tab.def.icon,
                          color: tab.visible
                              ? theme.colorScheme.primary
                              : context.textSecondaryColor,
                        ),
                        title: Text(
                          label,
                          style: TextStyle(
                            fontWeight: tab.visible
                                ? FontWeight.w500
                                : FontWeight.normal,
                            color: tab.visible
                                ? context.textColor
                                : context.textSecondaryColor,
                          ),
                        ),
                        subtitle: isEffectivelyRequired
                            ? Text(
                                l10n.tabAlwaysShown,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: context.textSecondaryColor,
                                ),
                              )
                            : null,
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Switch.adaptive(
                              value: tab.visible,
                              onChanged: isEffectivelyRequired
                                  ? null
                                  : (_) => _toggle(tab),
                            ),
                            ReorderableDragStartListener(
                              index: index,
                              child: Padding(
                                padding: const EdgeInsets.all(8),
                                child: Icon(
                                  Icons.drag_handle,
                                  color: context.textSecondaryColor,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
              Divider(height: 1, color: context.borderColor),

              // ── Action buttons ────────────────────────────────────────
              SafeArea(
                top: false,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 16),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () => Navigator.of(context).pop(),
                          child: Text(l10n.cancel),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(
                          onPressed: _save,
                          child: Text(l10n.save),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
