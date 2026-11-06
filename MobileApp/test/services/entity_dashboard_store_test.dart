import 'dart:convert';
import 'dart:io';

import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/models/shared/assignment.dart';
import 'package:hum_databank_app/models/shared/entity.dart';
import 'package:hum_databank_app/repositories/dashboard_repository.dart';
import 'package:hum_databank_app/services/offline/entity_dashboard_store.dart';
import 'package:hum_databank_app/services/offline/offline_form_store.dart';

Assignment assignment(int id, int templateId, {DateTime? due}) => Assignment(
  id: id,
  name: 'Form $id',
  status: 'pending',
  completionRate: 0,
  templateId: templateId,
  dueDate: due,
);

void main() {
  late Directory tmp;
  late EntityDashboardStore store;
  final lebanon = Entity(entityType: 'country', entityId: 1, name: 'Lebanon');
  final jordan = Entity(entityType: 'country', entityId: 2, name: 'Jordan');

  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    await dotenv.load(fileName: '.env', isOptional: true);
  });

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('entity_dashboards_test');
    store = EntityDashboardStore(
      store: OfflineFormStore(baseDir: tmp, scope: 'user_1'),
    );
  });

  tearDown(() async {
    if (await tmp.exists()) await tmp.delete(recursive: true);
  });

  test('keeps a separate dashboard per entity', () async {
    await store.save(
      EntityDashboardSnapshot(
        entity: lebanon,
        currentAssignments: [assignment(1, 7)],
      ),
    );
    await store.save(
      EntityDashboardSnapshot(
        entity: jordan,
        currentAssignments: [assignment(2, 7)],
        pastAssignments: [assignment(3, 7)],
      ),
    );

    expect((await store.read(lebanon))!.currentAssignments.single.id, 1);
    final jordanSaved = (await store.read(jordan))!;
    expect(jordanSaved.currentAssignments.single.id, 2);
    expect(jordanSaved.pastAssignments.single.id, 3);
    expect(jordanSaved.entity, jordan);
  });

  test('an entity that was never saved has no dashboard', () async {
    expect(await store.read(lebanon), isNull);
  });

  test(
    'a newly downloaded template replaces only its own assignments',
    () async {
      await store.save(
        EntityDashboardSnapshot(
          entity: lebanon,
          currentAssignments: [assignment(1, 7), assignment(2, 8)],
        ),
      );

      await store.mergeTemplates(
        EntityDashboardSnapshot(
          entity: lebanon,
          currentAssignments: [assignment(5, 7)],
        ),
        {7},
      );

      final merged = (await store.read(lebanon))!;
      expect(merged.currentAssignments.map((a) => a.id), [2, 5]);
    },
  );

  test(
    'an entity never opened still gets the downloaded assignments',
    () async {
      await store.mergeTemplates(
        EntityDashboardSnapshot(
          entity: jordan,
          currentAssignments: [assignment(9, 7)],
        ),
        {7},
      );

      expect((await store.read(jordan))!.currentAssignments.single.id, 9);
    },
  );

  test(
    'snapshots are stored under the signed-in user and removed with it',
    () async {
      await store.save(EntityDashboardSnapshot(entity: lebanon));
      final dir = Directory('${tmp.path}/user_1/dashboards');
      expect(dir.listSync(), hasLength(1));

      await OfflineFormStore(baseDir: tmp, scope: 'user_1').deleteAll();

      expect(await store.read(lebanon), isNull);
    },
  );

  test(
    'merged assignments keep the server order (due date, then id)',
    () async {
      await store.save(
        EntityDashboardSnapshot(
          entity: lebanon,
          currentAssignments: [
            assignment(1, 8, due: DateTime.utc(2026, 3, 1)),
            assignment(2, 8),
          ],
        ),
      );

      await store.mergeTemplates(
        EntityDashboardSnapshot(
          entity: lebanon,
          currentAssignments: [
            assignment(5, 7, due: DateTime.utc(2026, 2, 1)),
            assignment(4, 7),
          ],
        ),
        {7},
      );

      expect((await store.read(lebanon))!.currentAssignments.map((a) => a.id), [
        5,
        1,
        2,
        4,
      ]);
    },
  );

  group('offline-entities response', () {
    final body = jsonEncode({
      'success': true,
      'data': {
        'truncated': false,
        'entities': [
          {
            'entity': {
              'entity_type': 'country',
              'entity_id': 4,
              'name': 'Syria',
              'display_name': 'Syria',
            },
            'current_assignments': [
              {
                'id': 40,
                'name': '2026 - Annual',
                'status': 'pending',
                'completion_rate': 12.5,
                'template_id': 7,
                'static_version': 'v1',
                'data_version': '2026-01-01T00:00:00+00:00',
              },
            ],
            'past_assignments': [],
            'ns_focal_points': [
              {'id': 1, 'name': 'A', 'email': 'a@example.org'},
            ],
          },
        ],
      },
    });

    test('is parsed from the mobile envelope', () {
      final parsed = DashboardRepository.parseOfflineEntityDashboards(body);

      expect(parsed, hasLength(1));
      expect(parsed.single.entity.entityId, 4);
      expect(parsed.single.currentAssignments.single.templateId, 7);
      expect(parsed.single.nsFocalPoints.single.email, 'a@example.org');
    });

    test('is parsed without the envelope too', () {
      final inner = jsonEncode(jsonDecode(body)['data']);
      expect(
        DashboardRepository.parseOfflineEntityDashboards(inner),
        hasLength(1),
      );
    });

    test('rejects anything that is not an object', () {
      expect(
        () => DashboardRepository.parseOfflineEntityDashboards('[]'),
        throwsFormatException,
      );
    });
  });
}
