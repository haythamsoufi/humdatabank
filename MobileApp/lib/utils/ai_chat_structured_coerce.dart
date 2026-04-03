// Coerces AI structured payloads (maps/charts/tables) — Dart port of Backoffice chatbot.js _coerceStructuredPayload.

Map<String, dynamic>? coerceStructuredPayload(dynamic payload) {
  if (payload == null || payload is! Map) return null;
  final m = Map<String, dynamic>.from(payload as Map);

  final tp = m['table_payload'];
  if (tp is Map) {
    final t = Map<String, dynamic>.from(tp);
    if ((t['type']?.toString().toLowerCase() ?? '') == 'data_table' && t['rows'] is List) {
      return Map<String, dynamic>.from(t);
    }
  }

  Map<String, dynamic>? root;
  if (m['chart_payload'] is Map) {
    root = Map<String, dynamic>.from(m['chart_payload'] as Map);
  } else if (m['map_payload'] is Map) {
    root = Map<String, dynamic>.from(m['map_payload'] as Map);
  } else {
    root = Map<String, dynamic>.from(m);
  }

  final type = (root['type'] ?? root['map_type'] ?? root['chart_type'] ?? '').toString().toLowerCase();
  if (type == 'data_table' && root['rows'] is List) return root;

  final isWorldMap = type.isEmpty || type == 'worldmap' || type == 'world_map' || type == 'choropleth';
  final isLineChart = type == 'line' || type == 'linechart' || type == 'timeseries';
  final isBarChart = type == 'bar' || type == 'barchart';
  final isPieChart = type == 'pie' || type == 'donut';

  if (isBarChart) {
    final cats = root['categories'];
    if (cats is! List || cats.length < 2) return null;
    final categories = <Map<String, dynamic>>[];
    for (final c in cats) {
      if (c is! Map) continue;
      final label = (c['label'] ?? c['name'] ?? '').toString().trim();
      final value = _toDouble(c['value']);
      if (label.isEmpty || value == null) continue;
      categories.add({'label': label, 'value': value});
    }
    if (categories.length < 2) return null;
    return {
      'type': 'bar',
      'title': (root['title'] ?? 'Comparison').toString().trim(),
      'metric': (root['metric'] ?? 'Value').toString().trim(),
      'categories': categories,
      'orientation': (root['orientation'] ?? (categories.length > 6 ? 'horizontal' : 'vertical')).toString(),
    };
  }

  if (isPieChart) {
    final raw = root['slices'] is List ? root['slices'] as List : (root['data'] is List ? root['data'] as List : <dynamic>[]);
    if (raw.length < 2) return null;
    final slices = <Map<String, dynamic>>[];
    for (final s in raw) {
      if (s is! Map) continue;
      final label = (s['label'] ?? s['name'] ?? '').toString().trim();
      final value = _toDouble(s['value']);
      if (label.isEmpty || value == null || value < 0) continue;
      slices.add({'label': label, 'value': value});
    }
    if (slices.length < 2) return null;
    return {
      'type': 'pie',
      'title': (root['title'] ?? 'Distribution').toString().trim(),
      'slices': slices,
    };
  }

  if (isLineChart) {
    final rows = root['series'] is List
        ? root['series'] as List
        : (root['data'] is List
            ? root['data'] as List
            : (root['points'] is List ? root['points'] as List : <dynamic>[]));
    if (rows.isEmpty) return null;
    final series = <Map<String, dynamic>>[];
    for (final row in rows) {
      if (row is! Map) continue;
      final x = _extractYear(row['x'] ?? row['year'] ?? row['period']);
      var rawY = row['y'] ?? row['value'];
      if (rawY is String) rawY = rawY.replaceAll(',', '').trim();
      final y = _toDouble(rawY);
      if (x == null || y == null) continue;
      series.add({
        'x': x,
        'y': y,
        if (row['data_status'] != null) 'data_status': row['data_status'],
        if (row['period_name'] != null) 'period_name': row['period_name'],
      });
    }
    series.sort((a, b) => ((a['x'] as num?) ?? 0).compareTo((b['x'] as num?) ?? 0));
    if (series.isEmpty) return null;
    return {
      'type': 'line',
      'title': (root['title'] ?? 'Trend').toString().trim().isEmpty ? 'Trend' : (root['title'] ?? 'Trend').toString().trim(),
      'metric': (root['metric'] ?? root['y_label'] ?? 'value').toString().trim().isEmpty
          ? 'value'
          : (root['metric'] ?? root['y_label'] ?? 'value').toString().trim(),
      if ((root['country'] ?? '').toString().trim().isNotEmpty) 'country': root['country'].toString().trim(),
      'x': 'year',
      'y_label': (root['y_label'] ?? root['metric'] ?? 'value').toString().trim().isEmpty
          ? 'value'
          : (root['y_label'] ?? root['metric'] ?? 'value').toString().trim(),
      'series': series,
    };
  }

  if (!isWorldMap) return null;

  final rowList = root['countries'] is List
      ? root['countries'] as List
      : (root['locations'] is List
          ? root['locations'] as List
          : (root['data'] is List ? root['data'] as List : <dynamic>[]));
  if (rowList.isEmpty) return null;

  final countries = <Map<String, dynamic>>[];
  for (final row in rowList) {
    if (row is! Map) continue;
    var iso3 = (row['iso3'] ?? row['country_iso3'] ?? row['code'] ?? '').toString().trim().toUpperCase();
    if (iso3.length != 3) continue;
    var rawValue = row['value'];
    if (rawValue is String) rawValue = rawValue.replaceAll(',', '').trim();
    final value = _toDouble(rawValue);
    if (value == null) continue;
    final year = _extractYear(row['year'] ?? row['period_used'] ?? row['period']);
    final region = row['region']?.toString().trim();
    countries.add({
      'iso3': iso3,
      'value': value,
      'label': (row['label'] ?? row['name'] ?? iso3).toString().trim().isEmpty ? iso3 : (row['label'] ?? row['name'] ?? iso3).toString().trim(),
      if (year != null) 'year': year,
      if (region != null && region.isNotEmpty) 'region': region,
    });
  }
  if (countries.isEmpty) return null;

  return {
    'type': 'worldmap',
    'title': (root['title'] ?? 'World map').toString().trim().isEmpty ? 'World map' : (root['title'] ?? 'World map').toString().trim(),
    'metric': (root['metric'] ?? root['value_field'] ?? 'value').toString().trim().isEmpty
        ? 'value'
        : (root['metric'] ?? root['value_field'] ?? 'value').toString().trim(),
    'countries': countries,
  };
}

double? _toDouble(dynamic v) {
  if (v == null) return null;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString().replaceAll(',', '').trim());
}

int? _extractYear(dynamic v) {
  if (v == null) return null;
  if (v is num) {
    final y = v.round();
    if (y >= 1900 && y <= 2100) return y;
  }
  final s = v.toString();
  final re = RegExp(r'\b(19\d{2}|20\d{2})\b');
  final ms = re.allMatches(s).map((m) => int.tryParse(m.group(0)!)).whereType<int>().toList();
  if (ms.isEmpty) return null;
  return ms.reduce((a, b) => a > b ? a : b);
}

/// Merge zero or more WS/SSE keys into normalized structured maps (dedupe by JSON string).
List<Map<String, dynamic>> coerceStructuredFromEnvelope(Map<String, dynamic> data) {
  final out = <Map<String, dynamic>>[];
  final seen = <String>{};

  void addRaw(String key) {
    final raw = data[key];
    if (raw is! Map) return;
    final wrapped = coerceStructuredPayload({key: raw});
    if (wrapped == null) return;
    final sig = wrapped.toString();
    if (seen.contains(sig)) return;
    seen.add(sig);
    out.add(wrapped);
  }

  addRaw('table_payload');
  addRaw('chart_payload');
  addRaw('map_payload');

  final meta = data['meta'];
  if (meta is Map) {
    final mm = Map<String, dynamic>.from(meta);
    for (final k in ['table_payload', 'chart_payload', 'map_payload']) {
      final raw = mm[k];
      if (raw is Map) {
        final wrapped = coerceStructuredPayload({k: raw});
        if (wrapped != null) {
          final sig = wrapped.toString();
          if (!seen.contains(sig)) {
            seen.add(sig);
            out.add(wrapped);
          }
        }
      }
    }
  }

  return out;
}
