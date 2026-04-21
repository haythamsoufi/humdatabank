// World polygons: simplified Natural-Earth–style GeoJSON (Holtzy D3 gallery),
// bundled for offline choropleth. ISO3 `id` per feature; Kosovo `OSA` → XK.
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

/// Bundled world country polygons (ISO3 `id` in GeoJSON) mapped to ISO2 for FDRS joins.
class WorldGeoJsonCache {
  WorldGeoJsonCache._();
  static final WorldGeoJsonCache instance = WorldGeoJsonCache._();

  /// Holtzy world.geojson uses `OSA` for Kosovo; map to user-assigned ISO2 used in REST/backoffice.
  static const Map<String, String> _iso3Overrides = {'OSA': 'XK'};

  bool _loaded = false;
  late List<WorldCountryPolygonShell> _shells;
  late Map<String, String> _iso3ToIso2;

  Future<void> ensureLoaded() async {
    if (_loaded) return;

    final isoRaw =
        await rootBundle.loadString('assets/data/iso3_to_iso2.json');
    final isoDecoded = jsonDecode(isoRaw);
    final isoMap = <String, String>{};
    if (isoDecoded is Map<String, dynamic>) {
      isoDecoded.forEach((k, v) {
        if (k.isNotEmpty && v != null) {
          isoMap[k.toUpperCase()] = v.toString().toUpperCase();
        }
      });
    }
    _iso3ToIso2 = {...isoMap, ..._iso3Overrides};

    final geoRaw =
        await rootBundle.loadString('assets/data/world_countries.geojson');
    final geoDecoded = jsonDecode(geoRaw);
    if (geoDecoded is! Map<String, dynamic>) {
      _shells = [];
      _loaded = true;
      return;
    }
    final features = geoDecoded['features'];
    if (features is! List<dynamic>) {
      _shells = [];
      _loaded = true;
      return;
    }

    final shells = <WorldCountryPolygonShell>[];
    for (final f in features) {
      if (f is! Map<String, dynamic>) continue;
      final iso3 = (f['id'] ?? f['properties']?['iso_a3'] ?? '')
          .toString()
          .toUpperCase();
      if (iso3.isEmpty) continue;
      final iso2 = _iso3ToIso2[iso3];
      if (iso2 == null || iso2.isEmpty) continue;

      final geom = f['geometry'];
      if (geom is! Map<String, dynamic>) continue;
      final type = geom['type']?.toString();
      final coords = geom['coordinates'];
      if (type == 'Polygon') {
        _addPolygonShells(shells, iso2, coords);
      } else if (type == 'MultiPolygon') {
        if (coords is List<dynamic>) {
          for (final poly in coords) {
            _addPolygonShells(shells, iso2, poly);
          }
        }
      }
    }
    _shells = shells;
    _loaded = true;
  }

  void _addPolygonShells(
    List<WorldCountryPolygonShell> out,
    String iso2,
    dynamic coordinates,
  ) {
    if (coordinates is! List<dynamic> || coordinates.isEmpty) return;
    final rings = <List<LatLng>>[];
    for (final ring in coordinates) {
      if (ring is! List<dynamic>) continue;
      final pts = _ringToLatLng(ring);
      if (pts.length >= 3) rings.add(pts);
    }
    if (rings.isEmpty) return;
    final outer = rings.first;
    final holes = rings.length > 1 ? rings.sublist(1) : <List<LatLng>>[];
    out.add(WorldCountryPolygonShell(iso2: iso2, outer: outer, holes: holes));
  }

  List<LatLng> _ringToLatLng(List<dynamic> ring) {
    final pts = <LatLng>[];
    for (final p in ring) {
      if (p is! List || p.length < 2) continue;
      final lon = (p[0] as num).toDouble();
      final lat = (p[1] as num).toDouble();
      pts.add(LatLng(lat, lon));
    }
    return pts;
  }

  /// One outline (plus optional holes) for a country; MultiPolygon becomes multiple shells.
  List<WorldCountryPolygonShell> get shells {
    assert(_loaded, 'Call ensureLoaded() first');
    return _shells;
  }

  /// Filled polygons for choropleth + hit testing ([hitValue] is ISO2).
  List<Polygon<String>> buildChoroplethPolygons({
    required Color fillNoData,
    required Color fillLow,
    required Color fillHigh,
    required Map<String, double> valueByIso2Upper,
    required double maxValue,
    double borderStrokeWidth = 0.6,
    required Color borderColor,
  }) {
    final maxV = maxValue <= 0 ? 1.0 : maxValue;
    final polys = <Polygon<String>>[];
    for (final s in shells) {
      final v = valueByIso2Upper[s.iso2];
      final Color fill;
      if (v == null || v <= 0) {
        fill = fillNoData;
      } else {
        final t = (v / maxV).clamp(0.0, 1.0);
        fill = Color.lerp(fillLow, fillHigh, t) ?? fillHigh;
      }
      polys.add(
        Polygon<String>(
          points: s.outer,
          holePointsList: s.holes.isEmpty ? null : s.holes,
          color: fill,
          borderStrokeWidth: borderStrokeWidth,
          borderColor: borderColor,
          hitValue: s.iso2,
        ),
      );
    }
    return polys;
  }
}

class WorldCountryPolygonShell {
  const WorldCountryPolygonShell({
    required this.iso2,
    required this.outer,
    required this.holes,
  });

  final String iso2;
  final List<LatLng> outer;
  final List<List<LatLng>> holes;
}
