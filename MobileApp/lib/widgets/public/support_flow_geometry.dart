import 'dart:math' as math;

import '../../models/public/support_flow.dart';

/// Geographic point used while bundling support lines. Longitude may sit
/// outside −180..180 while a path is still continuous across the date line.
class FlowPoint {
  final double lat;
  final double lng;

  const FlowPoint(this.lat, this.lng);
}

/// One bundled tree edge, already split where it crosses the date line.
class FlowDrawSegment {
  final String source;
  final List<String> destinations;
  final double weight;
  final bool leaf;
  final String? host;
  final List<List<FlowPoint>> parts;

  const FlowDrawSegment({
    required this.source,
    required this.destinations,
    required this.weight,
    required this.leaf,
    required this.parts,
    this.host,
  });
}

const _trunk = 0.4;
const _split = 0.68;
const _samples = 14;

double _nearLng(double lng, double origin) {
  var x = lng;
  while (x - origin > 180) {
    x -= 360;
  }
  while (origin - x > 180) {
    x += 360;
  }
  return x;
}

double wrapFlowLng(double lng) {
  return ((lng + 180) % 360 + 360) % 360 - 180;
}

/// Split a continuous path so a hop across ±180° is two pieces, one on each
/// edge of the map, instead of one line across every continent.
List<List<FlowPoint>> splitFlowAtAntimeridian(List<FlowPoint> points) {
  final parts = <List<FlowPoint>>[];
  final part = <FlowPoint>[];
  for (var i = 0; i < points.length; i++) {
    final point = points[i];
    if (part.isEmpty) {
      part.add(FlowPoint(point.lat, wrapFlowLng(point.lng)));
      continue;
    }
    final prev = points[i - 1];
    final boundary = _dateLineBetween(prev.lng, point.lng);
    if (boundary == null) {
      part.add(FlowPoint(point.lat, wrapFlowLng(point.lng)));
      continue;
    }
    final east = point.lng > prev.lng;
    final t = (boundary - prev.lng) / (point.lng - prev.lng);
    final latEdge = prev.lat + (point.lat - prev.lat) * t;
    part.add(FlowPoint(latEdge, east ? 180 : -180));
    if (part.length > 1) parts.add(List<FlowPoint>.from(part));
    part
      ..clear()
      ..add(FlowPoint(latEdge, east ? -180 : 180))
      ..add(FlowPoint(point.lat, wrapFlowLng(point.lng)));
  }
  if (part.length > 1) parts.add(List<FlowPoint>.from(part));
  return parts;
}

double? _dateLineBetween(double a, double b) {
  final lo = math.min(a, b);
  final hi = math.max(a, b);
  final boundary = 180 + 360 * ((lo - 180) / 360).ceil();
  if (boundary > lo && boundary <= hi) return boundary.toDouble();
  return null;
}

class _Cluster {
  _Cluster.leaf({
    required String hostIso,
    required this.weight,
    required this.clat,
    required this.clng,
  })  : leaf = true,
        host = hostIso,
        destSet = [hostIso],
        children = const <_Cluster>[];

  _Cluster.branch({
    required this.children,
    required this.weight,
    required this.clat,
    required this.clng,
    required this.destSet,
  })  : leaf = false,
        host = null;

  final bool leaf;
  final String? host;
  final double weight;
  final double clat;
  final double clng;
  final List<String> destSet;
  final List<_Cluster> children;
  List<double>? point;
}

_Cluster _clusterTree(List<_Cluster> leaves) {
  final nodes = List<_Cluster>.from(leaves);
  while (nodes.length > 1) {
    var bi = 0;
    var bj = 1;
    var best = double.infinity;
    for (var i = 0; i < nodes.length; i++) {
      for (var j = i + 1; j < nodes.length; j++) {
        final dLat = nodes[i].clat - nodes[j].clat;
        final dLng = _nearLng(nodes[j].clng, nodes[i].clng) - nodes[i].clng;
        final distance = dLat * dLat + dLng * dLng;
        if (distance < best) {
          best = distance;
          bi = i;
          bj = j;
        }
      }
    }
    final a = nodes[bi];
    final b = nodes[bj];
    final weight = a.weight + b.weight;
    final bLng = _nearLng(b.clng, a.clng);
    final parent = _Cluster.branch(
      children: [a, b],
      weight: weight,
      clat: (a.clat * a.weight + b.clat * b.weight) / weight,
      clng: (a.clng * a.weight + bLng * b.weight) / weight,
      destSet: [...a.destSet, ...b.destSet],
    );
    final hi = math.max(bi, bj);
    final lo = math.min(bi, bj);
    nodes
      ..removeAt(hi)
      ..removeAt(lo)
      ..add(parent);
  }
  return nodes.first;
}

void _assignMerge(_Cluster node, List<double> up, bool isRoot) {
  if (node.leaf) {
    node.point = [node.clat, _nearLng(node.clng, up[1])];
    return;
  }
  final ratio = isRoot ? _trunk : _split;
  node.point = [
    up[0] + (node.clat - up[0]) * ratio,
    up[1] + (_nearLng(node.clng, up[1]) - up[1]) * ratio,
  ];
  for (final child in node.children) {
    _assignMerge(child, node.point!, false);
  }
}

_Cluster _heaviestChild(_Cluster node) {
  return node.children[0].weight >= node.children[1].weight
      ? node.children[0]
      : node.children[1];
}

class _RawSegment {
  _RawSegment({
    required this.source,
    required this.destSet,
    required this.weight,
    required this.leaf,
    required this.p0,
    required this.p1,
    required this.p2,
    required this.p3,
    this.host,
  });

  final String source;
  final List<String> destSet;
  final double weight;
  final bool leaf;
  final String? host;
  final List<double> p0;
  final List<double> p1;
  final List<double> p2;
  final List<double> p3;
}

void _emit(
  _Cluster node,
  List<double> parentPoint,
  List<double> grandPoint,
  String source,
  List<_RawSegment> out,
) {
  final next = node.leaf ? node.point! : _heaviestChild(node).point!;
  out.add(_RawSegment(
    source: source,
    destSet: node.destSet,
    weight: node.weight,
    leaf: node.leaf,
    host: node.leaf ? node.host : null,
    p0: grandPoint,
    p1: parentPoint,
    p2: node.point!,
    p3: next,
  ));
  if (!node.leaf) {
    for (final child in node.children) {
      _emit(child, node.point!, parentPoint, source, out);
    }
  }
}

List<FlowPoint> _catmull(_RawSegment segment) {
  final origin = segment.p1[1];
  final p0 = [segment.p0[0], _nearLng(segment.p0[1], origin)];
  final p1 = [segment.p1[0], _nearLng(segment.p1[1], origin)];
  final p2 = [segment.p2[0], _nearLng(segment.p2[1], p1[1])];
  final p3 = [segment.p3[0], _nearLng(segment.p3[1], p2[1])];
  final out = <FlowPoint>[];
  for (var k = 0; k <= _samples; k++) {
    final t = k / _samples;
    final t2 = t * t;
    final t3 = t2 * t;
    out.add(FlowPoint(
      0.5 *
          (2 * p1[0] +
              (-p0[0] + p2[0]) * t +
              (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
              (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
      0.5 *
          (2 * p1[1] +
              (-p0[1] + p2[1]) * t +
              (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
              (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
    ));
  }
  return out;
}

bool _shortArcEast(double srcLng, double destLng) {
  return _nearLng(destLng, srcLng) - srcLng >= 0;
}

/// Bundled donor → host curves for the current filter.
///
/// Destinations east and west of a society are separate trees so a trunk does
/// not cross the date line. Shared branches are drawn once.
List<FlowDrawSegment> buildSupportFlowSegments({
  required List<SupportFlowNode> nodes,
  required List<SupportFlowEdge> edges,
}) {
  final byIso = {for (final node in nodes) node.iso3: node};
  final bySource = <String, List<SupportFlowEdge>>{};
  for (final edge in edges) {
    if (byIso[edge.from] == null || byIso[edge.to] == null) continue;
    bySource.putIfAbsent(edge.from, () => []).add(edge);
  }
  final raw = <_RawSegment>[];
  for (final entry in bySource.entries) {
    final source = byIso[entry.key]!;
    final start = [source.lat, source.lng];
    final east = <_Cluster>[];
    final west = <_Cluster>[];
    for (final edge in entry.value) {
      final host = byIso[edge.to]!;
      final leaf = _Cluster.leaf(
        hostIso: edge.to,
        weight: edge.weight,
        clat: host.lat,
        clng: host.lng,
      );
      if (_shortArcEast(source.lng, host.lng)) {
        east.add(leaf);
      } else {
        west.add(leaf);
      }
    }
    for (final leaves in [east, west]) {
      if (leaves.isEmpty) continue;
      final root = _clusterTree(leaves);
      _assignMerge(root, start, true);
      _emit(root, start, start, source.iso3, raw);
    }
  }
  return [
    for (final segment in raw)
      FlowDrawSegment(
        source: segment.source,
        destinations: segment.destSet,
        weight: segment.weight,
        leaf: segment.leaf,
        host: segment.host,
        parts: splitFlowAtAntimeridian(_catmull(segment)),
      ),
  ];
}
