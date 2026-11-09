import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/tab_customization_provider.dart';
import '../providers/shared/auth_provider.dart';
import '../l10n/app_localizations.dart';
import '../theme/grouped_sheet_style.dart';
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
      // Theme turns on a handle above the sheet. This sheet draws its own.
      showDragHandle: false,
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
    if (!tab.visible &&
        _visibleCount >= TabCustomizationProvider.maxVisibleTabs) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content:
              Text(AppLocalizations.of(context)!.maximumTabsWarning),
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

    final titleColor = GroupedSheetStyle.titleColor(context);
    final muted = context.textSecondaryColor;
    final hairline = GroupedSheetStyle.hairline(context);

    return Theme(
      data: GroupedSheetStyle.controlsTheme(context),
      child: Container(
        decoration: GroupedSheetStyle.sheetDecoration(context),
        child: DraggableScrollableSheet(
          initialChildSize: 0.55,
          minChildSize: 0.35,
          maxChildSize: 0.85,
          expand: false,
          builder: (context, scrollController) {
            return Column(
              children: [
                const Center(child: GroupedSheetDragHandle()),
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 2, 8, 2),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          l10n.customizeTabs,
                          style: theme.textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            letterSpacing: -0.2,
                            color: titleColor,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: _resetToDefaults,
                        child: Text(l10n.resetToDefault),
                      ),
                    ],
                  ),
                ),
                Divider(height: 1, thickness: 0.5, color: hairline),
                Expanded(
                  child: ReorderableListView.builder(
                    scrollController: scrollController,
                    buildDefaultDragHandles: false,
                    padding: EdgeInsets.zero,
                    itemCount: _tabs.length,
                    onReorder: _onReorder,
                    proxyDecorator: (child, _, animation) {
                      return AnimatedBuilder(
                        animation: animation,
                        builder: (context, child) {
                          final lift = Curves.easeOut.transform(animation.value);
                          return Material(
                            elevation: 3 * lift,
                            color: GroupedSheetStyle.canvas(context),
                            shadowColor: Colors.black26,
                            child: child,
                          );
                        },
                        child: child,
                      );
                    },
                    itemBuilder: (context, index) {
                      final tab = _tabs[index];
                      final label = tab.def.getLabel(l10n);
                      final isEffectivelyRequired = tab.def.isRequired ||
                          _roleRequiredTabs.contains(tab.def.id);
                      final fg = tab.visible ? titleColor : muted;

                      return DecoratedBox(
                        key: ValueKey(tab.def.id),
                        decoration: BoxDecoration(
                          border: Border(
                            bottom: BorderSide(color: hairline, width: 0.5),
                          ),
                        ),
                        child: SizedBox(
                          height: 48,
                          child: Padding(
                            padding: const EdgeInsets.only(left: 20, right: 4),
                            child: Row(
                              children: [
                                Icon(
                                  tab.visible
                                      ? tab.def.activeIcon
                                      : tab.def.icon,
                                  size: 20,
                                  color: fg,
                                ),
                                const SizedBox(width: 14),
                                Expanded(
                                  child: Text(
                                    label,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: theme.textTheme.bodyLarge?.copyWith(
                                      fontWeight: FontWeight.w400,
                                      color: fg,
                                    ),
                                  ),
                                ),
                                Switch.adaptive(
                                  value: tab.visible,
                                  materialTapTargetSize:
                                      MaterialTapTargetSize.shrinkWrap,
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
                                      size: 18,
                                      color: muted.withValues(alpha: 0.7),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
                SafeArea(
                  top: false,
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
                    child: Row(
                      children: [
                        TextButton(
                          onPressed: () => Navigator.of(context).pop(),
                          child: Text(l10n.cancel),
                        ),
                        const Spacer(),
                        TextButton(
                          onPressed: _save,
                          child: Text(
                            l10n.save,
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: titleColor,
                            ),
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
      ),
    );
  }
}
