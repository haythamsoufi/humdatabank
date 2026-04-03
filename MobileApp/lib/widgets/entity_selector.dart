import 'package:flutter/material.dart';
import '../models/shared/entity.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';

class EntitySelector extends StatelessWidget {
  final List<Entity> entities;
  final Entity? selectedEntity;
  final Function(Entity) onEntitySelected;

  const EntitySelector({
    super.key,
    required this.entities,
    this.selectedEntity,
    required this.onEntitySelected,
  });

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

  List<DropdownMenuItem<Entity>> _buildGroupedEntityItems(BuildContext context) {
    // Group entities by type
    final groupedEntities = <String, List<Entity>>{};
    for (final entity in entities) {
      final type = entity.entityType;
      if (!groupedEntities.containsKey(type)) {
        groupedEntities[type] = [];
      }
      groupedEntities[type]!.add(entity);
    }

    // Build dropdown items with groups
    final items = <DropdownMenuItem<Entity>>[];

    // Sort entity types for consistent ordering
    final sortedTypes = groupedEntities.keys.toList()..sort();

    for (final type in sortedTypes) {
      final typeEntities = groupedEntities[type]!;

      // Add header for entity type (non-selectable, using a dummy entity)
      // We'll use a special value to identify headers
      items.add(
        DropdownMenuItem<Entity>(
          enabled: false,
          value: null, // Headers have null value
          child: Container(
            padding:
                const EdgeInsets.symmetric(vertical: 8.0, horizontal: 12.0),
            decoration: BoxDecoration(
              color: context.subtleSurfaceColor,
              border: Border(
                bottom: BorderSide(
                  color: context.borderColor,
                  width: 1,
                ),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  _getEntityIcon(type),
                  size: 16,
                  color: Color(AppConstants.ifrcRed),
                ),
                const SizedBox(width: 8),
                Text(
                  _getEntityTypeLabel(type),
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                    color: Color(AppConstants.ifrcRed),
                  ),
                ),
              ],
            ),
          ),
        ),
      );

      // Add entities under this type (no icons, just text)
      for (final entity in typeEntities) {
        items.add(
          DropdownMenuItem<Entity>(
            value: entity,
            child: Padding(
              padding: const EdgeInsets.only(left: 24.0, top: 4.0, bottom: 4.0),
              child: Text(
                entity.displayLabel,
                style: const TextStyle(
                  fontWeight: FontWeight.w500,
                  fontSize: 15,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ),
        );
      }
    }

    return items;
  }

  @override
  Widget build(BuildContext context) {
    if (entities.isEmpty) {
      return const SizedBox.shrink();
    }

    // If only one entity, show it as a card (read-only)
    if (entities.length == 1) {
      return Card(
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
        child: Padding(
          padding: const EdgeInsets.all(AppConstants.paddingMedium),
          child: Row(
            children: [
              Icon(
                _getEntityIcon(entities.first.entityType),
                color: Color(AppConstants.ifrcRed),
                size: 24,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  entities.first.displayLabel,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    // Multiple entities - show dropdown selector
    return Card(
      elevation: 2,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppConstants.paddingMedium),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.location_on,
                  color: Color(AppConstants.ifrcRed),
                  size: 20,
                ),
                const SizedBox(width: 8),
                Text(
                  'Select Entity',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: const Color(AppConstants.textSecondary),
                      ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Builder(
              builder: (context) {
                // Find the actual entity from the current list that matches selectedEntity
                // This ensures we're using the same instance from the items list
                // Since Entity now has proper equality, we can use contains or firstWhere
                Entity? matchingEntity;
                if (selectedEntity != null) {
                  try {
                    // Find the entity from the current entities list that matches
                    matchingEntity = entities.firstWhere(
                      (e) => e == selectedEntity,
                      orElse: () => selectedEntity!,
                    );

                    // Verify it's actually in the items list (check all non-null items)
                    final items = _buildGroupedEntityItems(context);
                    final itemValues = items
                        .where((item) => item.value != null)
                        .map((item) => item.value!)
                        .toList();

                    // Use equality check to see if matchingEntity is in the list
                    if (!itemValues.contains(matchingEntity)) {
                      matchingEntity = null; // Don't use if not in list
                    }
                  } catch (e) {
                    // If there's any error finding the entity, set to null
                    matchingEntity = null;
                  }
                }

                return DropdownButtonFormField<Entity>(
                  initialValue: matchingEntity,
                  decoration: InputDecoration(
                    hintText: 'Choose an entity...',
                    prefixIcon: matchingEntity != null
                        ? Icon(
                            _getEntityIcon(matchingEntity.entityType),
                            color: Color(AppConstants.ifrcRed),
                          )
                        : null,
                    border: OutlineInputBorder(
                      borderRadius:
                          BorderRadius.circular(AppConstants.radiusMedium),
                    ),
                    filled: true,
                    fillColor: context.lightSurfaceColor,
                  ),
                  isExpanded: true,
                  menuMaxHeight: 400, // Limit dropdown height
                  items: _buildGroupedEntityItems(context),
                  onChanged: (Entity? entity) {
                    if (entity != null) {
                      onEntitySelected(entity);
                    }
                  },
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}
