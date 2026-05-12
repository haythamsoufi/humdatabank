import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/shared/notification.dart';
import '../../providers/shared/notification_provider.dart';
import '../../utils/notification_filter_types.dart';

/// Opens a bottom sheet to configure notification list filters.
Future<void> showNotificationFiltersSheet(BuildContext context) async {
  final loc = AppLocalizations.of(context)!;
  final provider = Provider.of<NotificationProvider>(context, listen: false);

  var unreadOnly = provider.filterUnreadOnly;
  String? notificationType = provider.filterNotificationType;
  String? priority = provider.filterPriority;
  var actorUserId = provider.filterActorUserId;

  await showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) {
      return Padding(
        padding: EdgeInsets.only(
          left: 20,
          right: 20,
          top: 8,
          bottom: MediaQuery.paddingOf(ctx).bottom + 16,
        ),
        child: StatefulBuilder(
          builder: (context, setModalState) {
            final actors = provider.distinctActorsForFilter;

            Widget labeledDropdown({
              required String label,
              required Widget child,
            }) {
              return InputDecorator(
                decoration: InputDecoration(
                  labelText: label,
                  border: const OutlineInputBorder(),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 4,
                  ),
                ),
                child: child,
              );
            }

            Widget typeDropdown() {
              return labeledDropdown(
                label: loc.notificationsFilterType,
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String?>(
                    isExpanded: true,
                    value: notificationType,
                    items: [
                      DropdownMenuItem<String?>(
                        value: null,
                        child: Text(loc.notificationsFilterTypeAny),
                      ),
                      ...kNotificationFilterTypeValues.map(
                        (v) => DropdownMenuItem<String?>(
                          value: v,
                          child: Text(formatNotificationTypeCode(v)),
                        ),
                      ),
                    ],
                    onChanged: (v) => setModalState(() => notificationType = v),
                  ),
                ),
              );
            }

            Widget priorityDropdown() {
              return labeledDropdown(
                label: loc.notificationsFilterPriority,
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<String?>(
                    isExpanded: true,
                    value: priority,
                    items: [
                      DropdownMenuItem<String?>(
                        value: null,
                        child: Text(loc.notificationsFilterPriorityAny),
                      ),
                      DropdownMenuItem<String?>(
                        value: 'normal',
                        child: Text(loc.notificationsFilterPriorityNormal),
                      ),
                      DropdownMenuItem<String?>(
                        value: 'high',
                        child: Text(loc.notificationsFilterPriorityHigh),
                      ),
                      DropdownMenuItem<String?>(
                        value: 'urgent',
                        child: Text(loc.notificationsFilterPriorityUrgent),
                      ),
                    ],
                    onChanged: (v) => setModalState(() => priority = v),
                  ),
                ),
              );
            }

            Widget fromDropdown() {
              return labeledDropdown(
                label: loc.notificationsFilterFrom,
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<int?>(
                    isExpanded: true,
                    value: actorUserId,
                    items: [
                      DropdownMenuItem<int?>(
                        value: null,
                        child: Text(loc.notificationsFilterFromAny),
                      ),
                      ...actors.map(
                        (NotificationActor a) => DropdownMenuItem<int?>(
                          value: a.id,
                          child: Text(
                            a.name.isNotEmpty ? a.name : 'User #${a.id}',
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ),
                    ],
                    onChanged: actors.isEmpty
                        ? null
                        : (v) => setModalState(() => actorUserId = v),
                  ),
                ),
              );
            }

            return SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    loc.notificationsFilterTitle,
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    loc.notificationsFilterReadStatus,
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  const SizedBox(height: 8),
                  SegmentedButton<bool>(
                    segments: [
                      ButtonSegment<bool>(
                        value: false,
                        label: Text(loc.notificationsFilterAll),
                      ),
                      ButtonSegment<bool>(
                        value: true,
                        label: Text(loc.notificationsFilterUnreadOnly),
                      ),
                    ],
                    selected: {unreadOnly},
                    onSelectionChanged: (s) {
                      setModalState(() => unreadOnly = s.first);
                    },
                  ),
                  const SizedBox(height: 16),
                  typeDropdown(),
                  const SizedBox(height: 12),
                  priorityDropdown(),
                  const SizedBox(height: 12),
                  fromDropdown(),
                  if (actors.isEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        loc.notificationsFilterFromEmptyHint,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () async {
                            Navigator.of(context).pop();
                            await provider.clearListFilters();
                          },
                          child: Text(loc.notificationsFilterReset),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton(
                          onPressed: () async {
                            Navigator.of(context).pop();
                            await provider.applyListFilters(
                              unreadOnly: unreadOnly,
                              notificationType: notificationType,
                              priority: priority,
                              actorUserId: actorUserId,
                            );
                          },
                          child: Text(loc.notificationsFilterApply),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        ),
      );
    },
  );
}
