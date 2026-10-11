import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../providers/shared/dashboard_provider.dart';
import '../models/shared/entity.dart';
import '../l10n/app_localizations.dart';
import '../theme/grouped_sheet_style.dart';
import '../utils/ios_constants.dart';
import 'app_fade_in_up.dart';

class EntityListItem {
  final bool isHeader;
  final String? entityType;
  final Entity? entity;

  EntityListItem({
    required this.isHeader,
    this.entityType,
    this.entity,
  });
}

class EntitySelectorBottomSheet extends StatefulWidget {
  final DashboardProvider provider;
  final ThemeData theme;
  final AppLocalizations localizations;

  const EntitySelectorBottomSheet({
    super.key,
    required this.provider,
    required this.theme,
    required this.localizations,
  });

  static void show(BuildContext context, DashboardProvider provider) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    HapticFeedback.selectionClick();

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => EntitySelectorBottomSheet(
        provider: provider,
        theme: theme,
        localizations: localizations,
      ),
    );
  }

  @override
  State<EntitySelectorBottomSheet> createState() =>
      _EntitySelectorBottomSheetState();
}

class _EntitySelectorBottomSheetState
    extends State<EntitySelectorBottomSheet> {
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

  List<EntityListItem> get _flatItemList {
    final List<EntityListItem> items = [];
    for (final sectionType in _sortedEntityTypes) {
      items.add(EntityListItem(isHeader: true, entityType: sectionType));
      final entities = _groupedEntities[sectionType]!;
      for (final entity in entities) {
        items.add(EntityListItem(isHeader: false, entity: entity));
      }
    }
    return items;
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
      decoration: GroupedSheetStyle.sheetDecoration(context),
      child: SafeArea(
        child: Column(
        children: [
          const GroupedSheetDragHandle(),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 12, 8),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    localizations.entities,
                    style: GroupedSheetStyle.title(context),
                  ),
                ),
                GroupedSheetCloseButton(
                  tooltip: localizations.close,
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: TextField(
              controller: _searchController,
              style: IOSTextStyle.subheadline(context).copyWith(
                color: widget.theme.colorScheme.onSurface,
              ),
              decoration: GroupedSheetStyle.fieldDecoration(
                context,
                hint: localizations.searchPlaceholder,
              ).copyWith(
                prefixIcon: Icon(
                  Icons.search_rounded,
                  color: widget.theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
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
                              .withValues(alpha: 0.4),
                        ),
                        SizedBox(height: IOSSpacing.mdOf(context)),
                        Text(
                          localizations.noResultsFound,
                          style: IOSTextStyle.subheadline(context).copyWith(
                            color: widget.theme.textTheme.bodyMedium?.color ??
                                widget.theme.colorScheme.onSurface
                                    .withValues(alpha: 0.6),
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

                      if (item.isHeader && item.entityType != null) {
                        return AppFadeInUp(
                          staggerIndex: index,
                          child: _buildSectionHeader(item.entityType!),
                        );
                      }

                      if (!item.isHeader && item.entity != null) {
                        final entity = item.entity!;
                        final isSelected =
                            widget.provider.selectedEntity?.entityType ==
                                    entity.entityType &&
                                widget.provider.selectedEntity?.entityId ==
                                    entity.entityId;

                        return AppFadeInUp(
                          staggerIndex: index,
                          child: Padding(
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            child: GroupedSheetOption(
                              label: entity.displayLabel,
                              selected: isSelected,
                              onTap: () {
                                final entityToSelect = entity;
                                final providerToUse = widget.provider;

                                Navigator.of(context).pop();

                                WidgetsBinding.instance
                                    .addPostFrameCallback((_) {
                                  providerToUse.selectEntity(entityToSelect);
                                });
                              },
                            ),
                          ),
                        );
                      }

                      return const SizedBox.shrink();
                    },
                  ),
          ),
        ],
      ),
      ),
    );
  }

  Widget _buildSectionHeader(String entityType) {
    final count = '${_groupedEntities[entityType]?.length ?? 0}';
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 8),
      child: Row(
        children: [
          Icon(
            _getEntityIcon(entityType),
            size: 16,
            color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.48),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: GroupedSheetSectionLabel(_getEntityTypeLabel(entityType)),
          ),
          Text(count, style: GroupedSheetStyle.section(context)),
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
    final localizations = AppLocalizations.of(context)!;
    switch (entityType.toLowerCase()) {
      case 'country':
        return localizations.entityTypeCountry;
      case 'ns_branch':
        return localizations.entityTypeNsBranch;
      case 'ns_subbranch':
        return localizations.entityTypeNsSubBranch;
      case 'ns_localunit':
        return localizations.entityTypeNsLocalUnit;
      case 'division':
        return localizations.entityTypeDivision;
      case 'department':
        return localizations.entityTypeDepartment;
      default:
        return entityType.toUpperCase();
    }
  }
}
