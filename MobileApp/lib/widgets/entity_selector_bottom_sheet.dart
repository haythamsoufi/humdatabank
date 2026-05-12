import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/services.dart';
import '../providers/shared/dashboard_provider.dart';
import '../models/shared/entity.dart';
import '../l10n/app_localizations.dart';
import '../utils/theme_extensions.dart';
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

    cupertino.showCupertinoModalPopup(
      context: context,
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
      decoration: BoxDecoration(
        color: widget.theme.scaffoldBackgroundColor,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          Container(
            margin: const EdgeInsets.only(top: 8, bottom: 4),
            width: 36,
            height: 5,
            decoration: BoxDecoration(
              color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(2.5),
            ),
          ),
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
          Padding(
            padding: EdgeInsets.fromLTRB(
              IOSSpacing.lgOf(context),
              IOSSpacing.smOf(context),
              IOSSpacing.lgOf(context),
              IOSSpacing.mdOf(context) - 4,
            ),
            child: cupertino.CupertinoSearchTextField(
              controller: _searchController,
              placeholder: localizations.searchPlaceholder,
              placeholderStyle: IOSTextStyle.subheadline(context).copyWith(
                color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.4),
              ),
              style: IOSTextStyle.subheadline(context).copyWith(
                color: widget.theme.colorScheme.onSurface,
              ),
              backgroundColor: widget.theme.colorScheme.onSurface.withValues(alpha: 0.06),
              itemColor: widget.theme.colorScheme.onSurface,
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
                          child: Material(
                            color: Colors.transparent,
                            child: InkWell(
                              onTap: () {
                                HapticFeedback.selectionClick();

                                final entityToSelect = entity;
                                final providerToUse = widget.provider;

                                Navigator.of(context).pop();

                                WidgetsBinding.instance
                                    .addPostFrameCallback((_) {
                                  providerToUse.selectEntity(entityToSelect);
                                });
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    vertical: IOSSpacing.sm + 6,
                                    horizontal: IOSSpacing.lg),
                                decoration: BoxDecoration(
                                  border: Border(
                                    bottom: BorderSide(
                                      color: widget.theme.dividerColor
                                          .withValues(alpha: 0.5),
                                      width: 0.5,
                                    ),
                                  ),
                                ),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        entity.displayLabel,
                                        style: IOSTextStyle.callout(context)
                                            .copyWith(
                                          fontWeight: isSelected
                                              ? FontWeight.w600
                                              : FontWeight.w400,
                                          color: isSelected
                                              ? (widget.theme.isDarkTheme
                                                  ? widget.theme.colorScheme
                                                      .tertiary
                                                  : context.navyTextColor)
                                              : widget.theme.colorScheme
                                                  .onSurface,
                                        ),
                                      ),
                                    ),
                                    if (isSelected)
                                      Icon(
                                        Icons.check_rounded,
                                        color: widget.theme.isDarkTheme
                                            ? widget.theme.colorScheme.tertiary
                                            : context.navyIconColor,
                                        size: 22,
                                      ),
                                  ],
                                ),
                              ),
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
        color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.04),
        border: Border(
          bottom: BorderSide(
            color: widget.theme.dividerColor.withValues(alpha: 0.3),
            width: 0.5,
          ),
        ),
      ),
      child: Row(
        children: [
          Icon(
            _getEntityIcon(entityType),
            size: 16,
            color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.6),
          ),
          SizedBox(width: IOSSpacing.smOf(context)),
          Text(
            _getEntityTypeLabel(entityType).toUpperCase(),
            style: IOSTextStyle.footnote(context).copyWith(
              fontWeight: FontWeight.w600,
              color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.6),
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
              color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              '${_groupedEntities[entityType]?.length ?? 0}',
              style: IOSTextStyle.caption2(context).copyWith(
                color: widget.theme.colorScheme.onSurface.withValues(alpha: 0.8),
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
