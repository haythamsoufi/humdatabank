import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:latlong2/latlong.dart';

/// Centroids keyed by ISO 3166-1 alpha-2 (uppercase), from bundled REST Countries data.
class CountryCentroidsCache {
  CountryCentroidsCache._();
  static final CountryCentroidsCache instance = CountryCentroidsCache._();

  Map<String, LatLng>? _byIso2;

  Future<void> ensureLoaded() async {
    if (_byIso2 != null) return;
    final raw =
        await rootBundle.loadString('assets/data/restcountries_latlng.json');
    final list = jsonDecode(raw) as List<dynamic>;
    final m = <String, LatLng>{};
    for (final e in list) {
      if (e is! Map<String, dynamic>) continue;
      final cca2 = (e['cca2'] as String?)?.toUpperCase();
      final ll = e['latlng'];
      if (cca2 == null || ll is! List || ll.length < 2) continue;
      m[cca2] = LatLng((ll[0] as num).toDouble(), (ll[1] as num).toDouble());
    }
    _byIso2 = m;
  }

  LatLng? operator [](String? iso2) {
    if (iso2 == null || iso2.isEmpty) return null;
    return _byIso2![iso2.toUpperCase()];
  }
}
