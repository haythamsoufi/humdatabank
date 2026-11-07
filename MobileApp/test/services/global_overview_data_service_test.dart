import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/services/global_overview_data_service.dart';

void main() {
  group('FdrsIndicatorSelection', () {
    test('bank selection queries by indicator bank id', () {
      expect(const FdrsIndicatorSelection.bank(724).queryParams, {
        'indicator_bank_id': '724',
      });
    });

    test('reach selection queries by KPI code', () {
      const selection = FdrsIndicatorSelection.reach(
        kpiCode: 'KPI_ReachH',
        sectorKey: '3',
        label: 'Health',
      );
      expect(selection.isReach, isTrue);
      expect(selection.queryParams, {'kpi_code': 'KPI_ReachH'});
    });

    test('equality ignores label and sector', () {
      const a = FdrsIndicatorSelection.reach(
        kpiCode: 'KPI_ReachH',
        sectorKey: '3',
        label: 'Health',
      );
      const b = FdrsIndicatorSelection.reach(
        kpiCode: 'KPI_ReachH',
        sectorKey: '3',
        label: 'Santé',
      );
      expect(a, b);
      expect(a == const FdrsIndicatorSelection.bank(724), isFalse);
    });
  });

  group('parseReachSectors', () {
    test('keeps sectors with indicators and falls back to other', () {
      final sectors = parseReachSectors({
        'data': {
          'sectors': [
            {
              'id': '4',
              'name': 'Health',
              'indicators': [
                {'kpi_code': 'KPI_ReachH', 'name': 'Health reach'},
                {'name': 'missing code'},
              ],
            },
            {
              'id': null,
              'name': null,
              'indicators': [
                {'kpi_code': 'KPI_ReachL', 'name': 'Livelihoods reach'},
              ],
            },
            {'id': '9', 'name': 'Empty', 'indicators': []},
          ],
        },
      });

      expect(sectors.map((s) => s.key), ['4', 'other']);
      expect(sectors.first.indicators.map((i) => i.kpiCode), ['KPI_ReachH']);
      expect(sectors.last.name, isNull);
    });

    test('returns empty for unexpected bodies', () {
      expect(parseReachSectors(null), isEmpty);
      expect(parseReachSectors({'data': []}), isEmpty);
    });
  });

  group('GlobalRollingMean.fromJson', () {
    test('parses the volunteers headline', () {
      final mean = GlobalRollingMean.fromJson({
        'value': 1234,
        'year_from': 2022,
        'year_to': 2024,
      });

      expect(mean, isNotNull);
      expect(mean!.value, 1234);
      expect(mean.yearFrom, 2022);
      expect(mean.yearTo, 2024);
    });

    test('returns null when absent or empty', () {
      expect(GlobalRollingMean.fromJson(null), isNull);
      expect(
        GlobalRollingMean.fromJson({
          'value': 0,
          'year_from': 2022,
          'year_to': 2024,
        }),
        isNull,
      );
    });
  });
}
