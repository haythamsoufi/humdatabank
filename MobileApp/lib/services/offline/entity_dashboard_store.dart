import 'dart:io';

import 'package:path/path.dart' as p;

import '../../models/shared/assignment.dart';
import '../../models/shared/dashboard_data.dart';
import '../../models/shared/entity.dart';
import '../../models/shared/focal_point_contact.dart';
import '../../utils/debug_logger.dart';
import 'offline_form_store.dart';

/// What the dashboard showed for one entity: its assignments and the contacts
/// of its country.
class EntityDashboardSnapshot {
  const EntityDashboardSnapshot({
    required this.entity,
    this.currentAssignments = const [],
    this.pastAssignments = const [],
    this.nsFocalPoints = const [],
    this.orgFocalPoints = const [],
    this.fdsMembers = const [],
    this.savedAt,
  });

  final Entity entity;
  final List<Assignment> currentAssignments;
  final List<Assignment> pastAssignments;
  final List<FocalPointContact> nsFocalPoints;
  final List<FocalPointContact> orgFocalPoints;
  final List<FocalPointContact> fdsMembers;
  final DateTime? savedAt;

  /// Every assignment of the entity, current first.
  Iterable<Assignment> get allAssignments sync* {
    yield* currentAssignments;
    yield* pastAssignments;
  }

  factory EntityDashboardSnapshot.fromData(DashboardData data, Entity entity) =>
      EntityDashboardSnapshot(
        entity: entity,
        currentAssignments: data.currentAssignments,
        pastAssignments: data.pastAssignments,
        nsFocalPoints: data.nsFocalPoints,
        orgFocalPoints: data.orgFocalPoints,
        fdsMembers: data.fdsMembers,
        savedAt: data.timestamp,
      );

  /// Parses one entry of the server's `offline-entities` response.
  factory EntityDashboardSnapshot.fromServerJson(Map<String, dynamic> json) {
    List<T> list<T>(String key, T Function(Map<String, dynamic>) parse) => [
      for (final item in (json[key] as List? ?? const []))
        if (item is Map) parse(Map<String, dynamic>.from(item)),
    ];
    return EntityDashboardSnapshot(
      entity: Entity.fromJson(Map<String, dynamic>.from(json['entity'] as Map)),
      currentAssignments: list('current_assignments', Assignment.fromJson),
      pastAssignments: list('past_assignments', Assignment.fromJson),
      nsFocalPoints: list('ns_focal_points', FocalPointContact.fromJson),
      orgFocalPoints: list('org_focal_points', FocalPointContact.fromJson),
      fdsMembers: list('fds_members', FocalPointContact.fromJson),
      savedAt: DateTime.now(),
    );
  }

  factory EntityDashboardSnapshot.fromJson(Map<String, dynamic> json) {
    final snapshot = EntityDashboardSnapshot.fromServerJson(json);
    return EntityDashboardSnapshot(
      entity: snapshot.entity,
      currentAssignments: snapshot.currentAssignments,
      pastAssignments: snapshot.pastAssignments,
      nsFocalPoints: snapshot.nsFocalPoints,
      orgFocalPoints: snapshot.orgFocalPoints,
      fdsMembers: snapshot.fdsMembers,
      savedAt: DateTime.tryParse(json['saved_at']?.toString() ?? ''),
    );
  }

  Map<String, dynamic> toJson() => {
    'saved_at': (savedAt ?? DateTime.now()).toUtc().toIso8601String(),
    'entity': entity.toJson(),
    'current_assignments': [for (final a in currentAssignments) a.toJson()],
    'past_assignments': [for (final a in pastAssignments) a.toJson()],
    'ns_focal_points': [for (final c in nsFocalPoints) c.toJson()],
    'org_focal_points': [for (final c in orgFocalPoints) c.toJson()],
    'fds_members': [for (final c in fdsMembers) c.toJson()],
  };

  DashboardData toDashboardData({required List<Entity> entities}) =>
      DashboardData(
        currentAssignments: currentAssignments,
        pastAssignments: pastAssignments,
        entities: entities,
        selectedEntity: entity,
        nsFocalPoints: nsFocalPoints,
        orgFocalPoints: orgFocalPoints,
        fdsMembers: fdsMembers,
        timestamp: savedAt,
      );

  /// This snapshot with the assignments of [templateIds] replaced by those of
  /// [fresh]; assignments of other templates are kept.
  EntityDashboardSnapshot withTemplatesFrom(
    EntityDashboardSnapshot fresh,
    Set<int> templateIds,
  ) {
    List<Assignment> merge(List<Assignment> mine, List<Assignment> theirs) {
      final kept = [
        for (final a in mine)
          if (a.templateId == null || !templateIds.contains(a.templateId)) a,
      ];
      return _sortLikeServer([...kept, ...theirs]);
    }

    return EntityDashboardSnapshot(
      entity: entity,
      currentAssignments: merge(currentAssignments, fresh.currentAssignments),
      pastAssignments: merge(pastAssignments, fresh.pastAssignments),
      nsFocalPoints: fresh.nsFocalPoints,
      orgFocalPoints: fresh.orgFocalPoints,
      fdsMembers: fresh.fdsMembers,
      savedAt: fresh.savedAt,
    );
  }

  static List<Assignment> _sortLikeServer(List<Assignment> items) {
    final sorted = List<Assignment>.of(items);
    sorted.sort((a, b) {
      final ad = a.dueDate;
      final bd = b.dueDate;
      if (ad == null && bd != null) return 1;
      if (ad != null && bd == null) return -1;
      if (ad != null && bd != null) {
        final byDue = ad.compareTo(bd);
        if (byDue != 0) return byDue;
      }
      return a.id.compareTo(b.id);
    });
    return sorted;
  }
}

/// Keeps one dashboard snapshot per entity on disk (for the signed-in user).
///
/// The dashboard API answers for one entity at a time, so without this a
/// device that is offline cannot show the assignments of any entity but the
/// one it last loaded, even when every one of their forms was downloaded.
class EntityDashboardStore {
  EntityDashboardStore({OfflineFormStore? store})
    : _store = store ?? OfflineFormStore();

  final OfflineFormStore _store;

  static String _fileName(Entity e) =>
      '${e.entityType.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_')}_${e.entityId}.json';

  Future<File> _file(Entity e) async =>
      File(p.join((await _store.entityDashboardsDir()).path, _fileName(e)));

  /// Replaces the saved dashboard of the snapshot's entity.
  Future<void> save(EntityDashboardSnapshot snapshot) async {
    try {
      await _store.writeJson(await _file(snapshot.entity), snapshot.toJson());
    } catch (e) {
      DebugLogger.logWarn('OFFLINE_STORE', 'Could not save dashboard: $e');
    }
  }

  /// Updates the saved dashboard with [fresh] assignments of [templateIds].
  /// An entity that was never opened gets a snapshot with just those.
  Future<void> mergeTemplates(
    EntityDashboardSnapshot fresh,
    Set<int> templateIds,
  ) async {
    final existing = await read(fresh.entity);
    await save(
      existing == null ? fresh : existing.withTemplatesFrom(fresh, templateIds),
    );
  }

  Future<EntityDashboardSnapshot?> read(Entity entity) async {
    final json = await _store.readJson(await _file(entity));
    if (json == null) return null;
    try {
      return EntityDashboardSnapshot.fromJson(json);
    } catch (e) {
      DebugLogger.logWarn('OFFLINE_STORE', 'Unreadable dashboard snapshot: $e');
      return null;
    }
  }
}
