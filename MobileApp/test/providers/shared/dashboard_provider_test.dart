import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/dashboard_data.dart';
import 'package:hum_databank_app/models/shared/entity.dart';
import 'package:hum_databank_app/providers/shared/dashboard_provider.dart';
import 'package:hum_databank_app/repositories/dashboard_repository.dart';

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
    this.apiData,
    this.validCache,
    this.staleCache,
  });

  final DashboardData? apiData;
  final DashboardData? validCache;
  final DashboardData? staleCache;
  final List<bool> cacheRequests = [];

  @override
  Future<DashboardData?> loadDashboardFromApi({Entity? entity}) async => apiData;

  @override
  Future<DashboardData?> loadDashboardFromCache({
    bool ignoreExpiry = false,
  }) async {
    cacheRequests.add(ignoreExpiry);
    return ignoreExpiry ? staleCache ?? validCache : validCache;
  }

  @override
  Future<void> saveDashboardToCache(DashboardData data) async {}

  @override
  Future<List<Entity>> loadEntitiesFromCache() async => const [];

  @override
  Future<void> clearCache() async {}

  @override
  Future<void> updateSelectedEntityStorage(Entity entity) async {}

  @override
  Future<Entity?> loadSelectedEntityFromStorage(List<Entity> entities) async =>
      null;
}
