import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/dashboard_data.dart';
import 'package:hum_databank_app/models/shared/entity.dart';
import 'package:hum_databank_app/providers/shared/dashboard_provider.dart';
import 'package:hum_databank_app/repositories/dashboard_repository.dart';
import 'package:hum_databank_app/services/offline/entity_dashboard_store.dart';

void main() {
  group('DashboardProvider offline fallback', () {
    test('force refresh hydrates an expired snapshot before a failed API call',
        () async {
      final cached = _dashboardWithAssignment(1, 'Saved assignment');
      final repository = _FakeDashboardRepository(staleCache: cached);
      final provider = DashboardProvider(repository: repository);

      await provider.loadDashboard(forceRefresh: true);

      expect(provider.currentAssignments, hasLength(1));
      expect(provider.currentAssignments.single.name, 'Saved assignment');
      expect(provider.error, isNull);
      expect(repository.cacheRequests, [true]);
    });

    test('failed normal refresh retries an expired snapshot', () async {
      final cached = _dashboardWithAssignment(2, 'Older assignment');
      final repository = _FakeDashboardRepository(staleCache: cached);
      final provider = DashboardProvider(repository: repository);

      await provider.loadDashboard();

      expect(provider.currentAssignments.single.id, 2);
      expect(provider.error, isNull);
      expect(repository.cacheRequests, [false, true]);
    });

    test('failed refresh still reports an error when no snapshot exists',
        () async {
      final provider = DashboardProvider(
        repository: _FakeDashboardRepository(),
      );

      await provider.loadDashboard(forceRefresh: true);

      expect(provider.currentAssignments, isEmpty);
      expect(
        provider.error,
        'Unable to load dashboard. Please check your connection and try again.',
      );
    });

    test('empty cached dashboard is treated as a valid offline snapshot',
        () async {
      final emptySnapshot = DashboardData(
        currentAssignments: const [],
        pastAssignments: const [],
        entities: const [],
        timestamp: DateTime(2026),
      );
      final provider = DashboardProvider(
        repository: _FakeDashboardRepository(staleCache: emptySnapshot),
      );

      await provider.loadDashboard(forceRefresh: true);

      expect(provider.currentAssignments, isEmpty);
      expect(provider.error, isNull);
    });
  });

  group('DashboardProvider entity selection', () {
    final a = Entity(entityType: 'country', entityId: 1, name: 'A');
    final b = Entity(entityType: 'country', entityId: 2, name: 'B');

    EntityDashboardSnapshot snapshotOf(Entity e, int assignmentId) =>
        EntityDashboardSnapshot(
          entity: e,
          currentAssignments: [
            Assignment(
              id: assignmentId,
              name: 'Saved for ${e.name}',
              status: 'pending',
              completionRate: 0,
              templateId: 7,
            ),
          ],
        );

    DashboardProvider providerWith(_FakeDashboardRepository repository) {
      final provider = DashboardProvider(repository: repository);
      return provider;
    }

    test(
      'offline, a saved entity dashboard opens without any request',
      () async {
        final repository = _FakeDashboardRepository(
          snapshots: {b.selectionKey: snapshotOf(b, 20)},
        );
        final provider = providerWith(repository);

        await provider.selectEntity(b, online: false);

        expect(provider.selectedEntity, b);
        expect(provider.currentAssignments.single.id, 20);
        expect(provider.error, isNull);
        expect(provider.isLoading, isFalse);
        expect(repository.apiRequests, isEmpty);
      },
    );

    test(
      'online, the saved dashboard shows first and is then refreshed',
      () async {
        final fresh = _dashboardWithAssignment(21, 'Fresh for B');
        final repository = _FakeDashboardRepository(
          snapshots: {b.selectionKey: snapshotOf(b, 20)},
          apiData: DashboardData(
            currentAssignments: fresh.currentAssignments,
            pastAssignments: const [],
            entities: [a, b],
            selectedEntity: b,
            timestamp: DateTime(2026),
          ),
        );
        final provider = providerWith(repository);
        final seen = <int>[];
        provider.addListener(() {
          if (provider.currentAssignments.isNotEmpty) {
            seen.add(provider.currentAssignments.single.id);
          }
        });

        await provider.selectEntity(b);

        expect(seen.first, 20);
        expect(provider.currentAssignments.single.id, 21);
        expect(repository.apiRequests, [b.selectionKey]);
      },
    );

    test('the previous entity\'s assignments never stay on screen', () async {
      final repository = _FakeDashboardRepository(
        snapshots: {a.selectionKey: snapshotOf(a, 10)},
      );
      final provider = providerWith(repository);
      await provider.selectEntity(a, online: false);
      expect(provider.currentAssignments.single.id, 10);

      await provider.selectEntity(b, online: false);

      expect(provider.currentAssignments, isEmpty);
      expect(provider.selectedEntity, b);
      expect(repository.assignmentsCleared, 1);
      expect(provider.error, isNotNull);
    });

    test(
      'an entity list survives selecting an entity with no saved data',
      () async {
        final repository = _FakeDashboardRepository(entities: [a, b]);
        final provider = providerWith(repository);
        await provider.loadEntities();

        await provider.selectEntity(b, online: false);

        expect(provider.entities, [a, b]);
      },
    );
  });
}

DashboardData _dashboardWithAssignment(int id, String name) {
  return DashboardData(
    currentAssignments: [
      Assignment(
        id: id,
        name: name,
        status: 'in_progress',
        completionRate: 0.5,
      ),
    ],
    pastAssignments: const [],
    entities: const [],
    timestamp: DateTime(2026),
  );
}

class _FakeDashboardRepository implements DashboardRepository {
  _FakeDashboardRepository({
    this.staleCache,
    this.apiData,
    Map<String, EntityDashboardSnapshot>? snapshots,
    this.entities = const [],
  }) : snapshots = snapshots ?? {};

  final DashboardData? staleCache;
  final DashboardData? apiData;
  final Map<String, EntityDashboardSnapshot> snapshots;
  final List<Entity> entities;
  final List<bool> cacheRequests = [];
  final List<String?> apiRequests = [];
  final List<DashboardData> saved = [];
  int assignmentsCleared = 0;

  @override
  Future<DashboardData?> loadDashboardFromApi({Entity? entity}) async {
    apiRequests.add(entity?.selectionKey);
    return apiData;
  }

  @override
  Future<DashboardData?> loadDashboardFromCache({
    bool ignoreExpiry = false,
  }) async {
    cacheRequests.add(ignoreExpiry);
    return ignoreExpiry ? staleCache : null;
  }

  @override
  Future<void> saveDashboardToCache(DashboardData data) async {
    saved.add(data);
  }

  @override
  Future<List<Entity>> loadEntitiesFromCache() async => entities;

  @override
  Future<void> clearCache() async {}

  @override
  Future<void> clearAssignmentsCache() async {
    assignmentsCleared++;
  }

  @override
  Future<EntityDashboardSnapshot?> loadEntitySnapshot(Entity entity) async =>
      snapshots[entity.selectionKey];

  @override
  Future<List<EntityDashboardSnapshot>> syncOfflineEntityDashboards({
    required Set<int> templateIds,
    int limit = 50,
  }) async => const [];

  @override
  Future<void> updateSelectedEntityStorage(Entity entity) async {}

  @override
  Future<Entity?> loadSelectedEntityFromStorage(List<Entity> entities) async =>
      null;
}
