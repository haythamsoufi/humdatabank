import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../config/app_config.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/public/support_flow.dart';
import '../../services/api_service.dart';
import '../../services/offline_cache_service.dart';
import '../../utils/theme_extensions.dart';
import '../home_landing/fdrs_world_map.dart';
import 'indicator_trend.dart';
import 'support_flow_geometry.dart';

const _donorColor = Color(0xFFF5333F);
const _hostColor = Color(0xFF011E41);
const _supportFlowEndpoint = '/upr/support-flow/data';

/// Pauses the parent scroll view while a finger is on the embedded map.
class InternationalMapPointerNotification extends Notification {
  InternationalMapPointerNotification({required this.activePointerCount});

  final int activePointerCount;
}

/// Native bilateral support map: year, supporting society and recipient
/// filters, bundled flow lines, priority bars and (for a PNS) network charts.
class SupportFlowPanel extends StatefulWidget {
  const SupportFlowPanel({
    super.key,
    required this.title,
    this.initialYear,
    this.initialPns,
    this.initialRecipient,
    this.showNetworkCharts = false,
  });

  final String title;
  final int? initialYear;
  final String? initialPns;
  final String? initialRecipient;

  /// Funding rankings and the INFORM coverage chart from the PNS overview.
  final bool showNetworkCharts;

  @override
  State<SupportFlowPanel> createState() => _SupportFlowPanelState();
}

class _SupportFlowPanelState extends State<SupportFlowPanel> {
  final ApiService _api = sl<ApiService>();
  final MapController _map = MapController();

  SupportFlowData? _data;
  bool _loading = true;
  bool _failed = false;
  bool _mapReady = false;
  int? _year;
  int? _baselineYear;
  String? _pns;
  String? _recipient;
  _FlowFocus? _focus;
  bool _nodeTapped = false;
  String? _segmentKey;
  List<FlowDrawSegment> _segments = const [];

  @override
  void initState() {
    super.initState();
    _year = widget.initialYear;
    _pns = _code(widget.initialPns);
    _recipient = _code(widget.initialRecipient);
    _load();
  }

  @override
  void dispose() {
    _map.dispose();
    super.dispose();
  }

  String? _code(String? raw) {
    final code = raw?.trim().toUpperCase() ?? '';
    if (code.length != 3) return null;
    return code;
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final response = await _api.get(
        _supportFlowEndpoint,
        includeAuth: false,
        cacheTtl: OfflineCacheService.publicBrowseTtl,
      );
      if (!mounted) return;
      final decoded = response.statusCode == 200
          ? jsonDecode(response.body)
          : null;
      if (decoded is! Map || decoded['success'] == false) {
        setState(() {
          _loading = false;
          _failed = true;
        });
        return;
      }
      final data = SupportFlowData.fromResponse(
        Map<String, dynamic>.from(decoded),
      );
      final year = _pickYear(data.years, _year ?? widget.initialYear);
      setState(() {
        _data = data;
        _loading = false;
        _failed = false;
        _year = year;
        _baselineYear = _pickYear(data.years, widget.initialYear);
        final resolved = _resolve(data);
        _pns = resolved.pns;
        _recipient = resolved.recipient;
        _segmentKey = null;
      });
      _scheduleFit();
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _failed = true;
      });
    }
  }

  int? _pickYear(List<int> years, int? preferred) {
    if (preferred != null && years.contains(preferred)) return preferred;
    if (years.contains(2026)) return 2026;
    if (years.isEmpty) return null;
    return years.first;
  }

  ({
    String? pns,
    String? recipient,
    List<SupportPartyOption> pnsOptions,
    List<SupportPartyOption> recipientOptions,
    List<SupportFlowEdge> edges,
  }) _resolve(SupportFlowData data) {
    final resolved = resolveSupportFlowFilter(
      data: data,
      year: _year,
      pns: _pns,
      recipient: _recipient,
    );
    return (
      pns: resolved.pns,
      recipient: resolved.recipient,
      pnsOptions: resolved.pnsOptions,
      recipientOptions: resolved.recipientOptions,
      edges: resolved.edges,
    );
  }

  void _apply({int? year, String? pns, String? recipient, bool clear = false}) {
    final data = _data;
    setState(() {
      _focus = null;
      if (clear) {
        _year = _baselineYear;
        _pns = null;
        _recipient = null;
      } else {
        if (year != null) _year = year;
        if (pns != null || _pns != null) _pns = pns;
        if (recipient != null || _recipient != null) _recipient = recipient;
      }
      if (data != null) {
        final resolved = _resolve(data);
        _pns = resolved.pns;
        _recipient = resolved.recipient;
      }
    });
    _scheduleFit();
  }

  bool get _filtersApplied =>
      _pns != null || _recipient != null || (_year != null && _year != _baselineYear);

  List<FlowDrawSegment> _segmentsFor(
    SupportFlowData data,
    List<SupportFlowEdge> edges,
    String? pns,
    String? recipient,
  ) {
    final key = '${_year ?? ''}|${pns ?? ''}|${recipient ?? ''}|${edges.length}';
    if (key == _segmentKey) return _segments;
    final nodes = supportNodesForEdges(data.nodes, edges);
    final built = buildSupportFlowSegments(nodes: nodes, edges: edges);
    _segmentKey = key;
    _segments = built;
    return built;
  }

  void _scheduleFit() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _fit();
    });
  }

  void _fit() {
    final data = _data;
    if (!_mapReady || data == null || _year == null) return;
    final nodes = supportNodesForEdges(data.nodes, _resolve(data).edges);
    if (nodes.isEmpty) return;
    final points = [for (final node in nodes) LatLng(node.lat, node.lng)];
    try {
      if (points.length == 1) {
        _map.move(points.first, 4);
        return;
      }
      _map.fitCamera(
        CameraFit.bounds(
          bounds: LatLngBounds.fromPoints(points),
          padding: const EdgeInsets.all(28),
          maxZoom: 5,
        ),
      );
    } catch (_) {
      // The map view is not attached yet.
    }
  }

  void _pinNode(SupportFlowNode node) {
    _nodeTapped = true;
    setState(() {
      _focus = node.outWeight > 0
          ? _FlowFocus.source(node.iso3)
          : _FlowFocus.host(node.iso3);
    });
  }

  void _onMapTap(TapPosition _, LatLng latlng) {
    if (_nodeTapped) {
      _nodeTapped = false;
      return;
    }
    final segment = _nearestSegment(latlng);
    setState(() {
      _focus = segment == null
          ? null
          : _FlowFocus.segment(segment.source, segment.destinations);
    });
  }

  FlowDrawSegment? _nearestSegment(LatLng tap) {
    if (!_mapReady || _segments.isEmpty) return null;
    final camera = _map.camera;
    final origin = camera.latLngToScreenOffset(tap);
    FlowDrawSegment? best;
    var bestDistance = 22.0;
    for (final segment in _segments) {
      for (final part in segment.parts) {
        for (final point in part) {
          final offset = camera.latLngToScreenOffset(LatLng(point.lat, point.lng));
          final distance = (offset - origin).distance;
          if (distance < bestDistance) {
            bestDistance = distance;
            best = segment;
          }
        }
      }
    }
    return best;
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          widget.title,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: context.navyTextColor,
          ),
        ),
        const SizedBox(height: 10),
        if (_loading) const _FlowStatusBox.loading(),
        if (_failed) _FlowStatusBox.error(onRetry: _load),
        if (!_loading && !_failed && _data != null) _buildLoaded(context, loc),
      ],
    );
  }

  Widget _buildLoaded(BuildContext context, AppLocalizations loc) {
    final data = _data!;
    if (!data.hasData || data.years.isEmpty || _year == null) {
      return Text(
        loc.countryDetailInternationalFlowEmpty,
        style: TextStyle(color: context.textSecondaryColor),
      );
    }
    final resolved = _resolve(data);
    final nodes = supportNodesForEdges(data.nodes, resolved.edges);
    final segments = _segmentsFor(
      data,
      resolved.edges,
      resolved.pns,
      resolved.recipient,
    );
    final figures = _figures(data, resolved.pns, resolved.recipient);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _FilterMenus(
          year: _year!,
          years: data.years,
          pns: resolved.pns,
          recipient: resolved.recipient,
          pnsOptions: resolved.pnsOptions,
          recipientOptions: resolved.recipientOptions,
          showClear: _filtersApplied,
          onYear: (year) => _apply(year: year, pns: _pns, recipient: _recipient),
          onPns: (iso) => _apply(pns: iso, recipient: _recipient),
          onRecipient: (iso) => _apply(pns: _pns, recipient: iso),
          onClear: () => _apply(clear: true),
        ),
        const SizedBox(height: 10),
        if (resolved.edges.isEmpty)
          Text(
            loc.countryDetailInternationalFlowEmpty,
            style: TextStyle(color: context.textSecondaryColor),
          )
        else
          _FlowMap(
            nodes: nodes,
            segments: segments,
            focus: _focus,
            onNodeTap: _pinNode,
            onMapTap: _onMapTap,
            onReset: _fit,
            onReady: () {
              _mapReady = true;
              _fit();
            },
            mapController: _map,
          ),
        const SizedBox(height: 8),
        _Legend(loc: loc),
        if (_focus != null) ...[
          const SizedBox(height: 8),
          _FocusCaption(
            label: _focusLabel(loc, data, resolved.edges),
            onClear: () => setState(() => _focus = null),
          ),
        ],
        const SizedBox(height: 14),
        _AreaBars(loc: loc, data: data, figures: figures),
        const SizedBox(height: 14),
        _FlowKpis(
          loc: loc,
          edges: resolved.edges,
          figures: figures,
        ),
        if (widget.showNetworkCharts) ...[
          const SizedBox(height: 20),
          _FundingRankings(
            loc: loc,
            data: data,
            year: _year!,
            pns: resolved.pns,
            recipient: resolved.recipient,
            onPns: (iso) => _apply(pns: iso, recipient: _recipient),
            onRecipient: (iso) => _apply(pns: _pns, recipient: iso),
          ),
          const SizedBox(height: 20),
          _CoverageChart(
            loc: loc,
            data: data,
            year: _year!,
            pns: resolved.pns,
            recipient: resolved.recipient,
            onRecipient: (iso) => _apply(pns: _pns, recipient: iso),
          ),
        ],
      ],
    );
  }

  List<SupportFlowFigure> _figures(
    SupportFlowData data,
    String? pns,
    String? recipient,
  ) {
    final year = _year;
    return [
      for (final row in data.figures)
        if (row.year == year &&
            (pns == null || row.from == pns) &&
            (recipient == null || row.to == recipient))
          row,
    ];
  }

  String _focusLabel(
    AppLocalizations loc,
    SupportFlowData data,
    List<SupportFlowEdge> edges,
  ) {
    final focus = _focus;
    if (focus == null) return '';
    final name = data.nodeByIso(focus.iso)?.name ?? focus.iso;
    if (focus.kind == _FlowFocusKind.host) {
      final count = edges.where((edge) => edge.to == focus.iso).length;
      return '$name · ${loc.countryDetailInternationalSupportingPns}: $count';
    }
    if (focus.kind == _FlowFocusKind.segment &&
        focus.destinations != null &&
        focus.destinations!.length == 1) {
      final host = data.nodeByIso(focus.destinations!.first)?.name ??
          focus.destinations!.first;
      return '$name → $host';
    }
    final count = focus.destinations?.length ??
        edges.where((edge) => edge.from == focus.iso).length;
    return '$name · ${loc.countryDetailInternationalCountriesSupported}: $count';
  }
}

class _FlowFocus {
  const _FlowFocus._(this.kind, this.iso, this.destinations);

  factory _FlowFocus.source(String iso) =>
      _FlowFocus._(_FlowFocusKind.source, iso, null);

  factory _FlowFocus.host(String iso) =>
      _FlowFocus._(_FlowFocusKind.host, iso, null);

  factory _FlowFocus.segment(String source, List<String> destinations) =>
      _FlowFocus._(_FlowFocusKind.segment, source, destinations);

  final _FlowFocusKind kind;
  final String iso;
  final List<String>? destinations;
}

enum _FlowFocusKind { source, host, segment }

bool _segmentHot(FlowDrawSegment segment, _FlowFocus? focus) {
  if (focus == null) return false;
  switch (focus.kind) {
    case _FlowFocusKind.host:
      return segment.destinations.contains(focus.iso);
    case _FlowFocusKind.source:
      return segment.source == focus.iso;
    case _FlowFocusKind.segment:
      if (segment.source != focus.iso) return false;
      final want = focus.destinations ?? const <String>[];
      return _covers(segment.destinations, want) ||
          _covers(want, segment.destinations);
  }
}

bool _covers(List<String> group, List<String> member) {
  if (member.isEmpty) return false;
  final set = group.toSet();
  return member.every(set.contains);
}

bool _nodeHot(SupportFlowNode node, List<FlowDrawSegment> segments, _FlowFocus? focus) {
  if (focus == null) return true;
  if (focus.kind != _FlowFocusKind.segment && node.iso3 == focus.iso) return true;
  if (focus.kind == _FlowFocusKind.segment && node.iso3 == focus.iso) return true;
  for (final segment in segments) {
    if (!_segmentHot(segment, focus)) continue;
    if (segment.source == node.iso3) return true;
    if (segment.leaf && segment.host == node.iso3) return true;
  }
  return false;
}

class _FilterMenus extends StatelessWidget {
  const _FilterMenus({
    required this.year,
    required this.years,
    required this.pns,
    required this.recipient,
    required this.pnsOptions,
    required this.recipientOptions,
    required this.showClear,
    required this.onYear,
    required this.onPns,
    required this.onRecipient,
    required this.onClear,
  });

  final int year;
  final List<int> years;
  final String? pns;
  final String? recipient;
  final List<SupportPartyOption> pnsOptions;
  final List<SupportPartyOption> recipientOptions;
  final bool showClear;
  final ValueChanged<int> onYear;
  final ValueChanged<String?> onPns;
  final ValueChanged<String?> onRecipient;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _LabeledMenu(
          label: loc.countryDetailInternationalFlowYear,
          value: '$year',
          entries: [for (final item in years) ('$item', '$item')],
          onChanged: (value) {
            final next = int.tryParse(value ?? '');
            if (next != null) onYear(next);
          },
        ),
        const SizedBox(height: 8),
        _LabeledMenu(
          label: loc.countryDetailInternationalFlowPns,
          value: pns ?? '',
          entries: [
            ('', loc.countryDetailInternationalFlowAll),
            for (final option in pnsOptions) (option.iso3, option.name),
          ],
          onChanged: (value) => onPns(value == null || value.isEmpty ? null : value),
        ),
        const SizedBox(height: 8),
        _LabeledMenu(
          label: loc.countryDetailInternationalFlowRecipient,
          value: recipient ?? '',
          entries: [
            ('', loc.countryDetailInternationalFlowAll),
            for (final option in recipientOptions) (option.iso3, option.name),
          ],
          onChanged: (value) =>
              onRecipient(value == null || value.isEmpty ? null : value),
        ),
        if (showClear)
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton.icon(
              onPressed: onClear,
              icon: const Icon(Icons.filter_alt_off, size: 18),
              label: Text(loc.countryDetailInternationalFlowClear),
            ),
          ),
      ],
    );
  }
}

class _LabeledMenu extends StatelessWidget {
  const _LabeledMenu({
    required this.label,
    required this.value,
    required this.entries,
    required this.onChanged,
  });

  final String label;
  final String value;
  final List<(String, String)> entries;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final safe = entries.any((entry) => entry.$1 == value) ? value : '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: theme.textTheme.labelMedium?.copyWith(
            color: context.textSecondaryColor,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 4),
        DecoratedBox(
          decoration: publicCardDecoration(context),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: DropdownButton<String>(
              value: safe,
              isExpanded: true,
              underline: const SizedBox.shrink(),
              menuMaxHeight: 320,
              borderRadius: BorderRadius.circular(12),
              items: [
                for (final entry in entries)
                  DropdownMenuItem(
                    value: entry.$1,
                    child: Text(
                      entry.$2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }
}

class _FlowMap extends StatelessWidget {
  const _FlowMap({
    required this.nodes,
    required this.segments,
    required this.focus,
    required this.onNodeTap,
    required this.onMapTap,
    required this.onReset,
    required this.onReady,
    required this.mapController,
  });

  final List<SupportFlowNode> nodes;
  final List<FlowDrawSegment> segments;
  final _FlowFocus? focus;
  final ValueChanged<SupportFlowNode> onNodeTap;
  final TapCallback onMapTap;
  final VoidCallback onReset;
  final VoidCallback onReady;
  final MapController mapController;

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final maxSegment = segments.fold<double>(1, (max, segment) {
      return segment.weight > max ? segment.weight : max;
    });
    final maxNode = nodes.fold<double>(1, (max, node) {
      return node.totalWeight > max ? node.totalWeight : max;
    });
    final ordered = [...segments]..sort((a, b) => b.weight.compareTo(a.weight));
    final polylines = <Polyline>[
      for (final segment in ordered)
        for (final part in segment.parts)
          if (part.length > 1)
            Polyline(
              points: [for (final point in part) LatLng(point.lat, point.lng)],
              strokeWidth: 1.2 + 6 * math.sqrt(segment.weight / maxSegment),
              color: _donorColor.withValues(
                alpha: focus == null
                    ? (segment.leaf ? 0.6 : 0.45)
                    : (_segmentHot(segment, focus) ? 0.95 : 0.08),
              ),
              strokeCap: StrokeCap.round,
              strokeJoin: StrokeJoin.round,
            ),
    ];
    final markers = <Marker>[
      for (final node in nodes)
        Marker(
          point: LatLng(node.lat, node.lng),
          width: _markerSize(node, maxNode),
          height: _markerSize(node, maxNode),
          child: GestureDetector(
            onTap: () => onNodeTap(node),
            child: DecoratedBox(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: (node.role == 'host' ? _hostColor : _donorColor).withValues(
                  alpha: _nodeHot(node, segments, focus) ? 0.95 : 0.2,
                ),
                border: Border.all(color: Colors.white, width: 1.2),
              ),
            ),
          ),
        ),
    ];

    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: DecoratedBox(
        decoration: publicCardDecoration(context),
        child: SizedBox(
          height: 320,
          child: Stack(
            children: [
              _MapPointerLock(
                child: FlutterMap(
                  mapController: mapController,
                  options: MapOptions(
                    initialCenter: const LatLng(20, 10),
                    initialZoom: 2,
                    minZoom: 1,
                    maxZoom: 6,
                    backgroundColor: Theme.of(context).colorScheme.surfaceContainerHigh,
                    cameraConstraint: CameraConstraint.contain(
                      bounds: LatLngBounds(
                        const LatLng(-85, -180),
                        const LatLng(85, 180),
                      ),
                    ),
                    interactionOptions: const InteractionOptions(
                      flags: InteractiveFlag.drag |
                          InteractiveFlag.pinchZoom |
                          InteractiveFlag.doubleTapZoom |
                          InteractiveFlag.flingAnimation,
                    ),
                    onTap: onMapTap,
                    onMapReady: onReady,
                  ),
                  children: [
                    ...fdrsWorldMapTiles(Theme.of(context)),
                    PolylineLayer(
                      polylines: polylines,
                      drawInSingleWorld: true,
                    ),
                    MarkerLayer(markers: markers),
                  ],
                ),
              ),
              PositionedDirectional(
                top: 8,
                end: 8,
                child: _MapTool(
                  tooltip: loc.countryDetailInternationalFlowReset,
                  icon: Icons.replay,
                  onPressed: onReset,
                ),
              ),
              PositionedDirectional(
                start: 6,
                bottom: 4,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: context.cardColor.withValues(alpha: 0.8),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                    child: Text(
                      AppConfig.mapboxAccessToken.isEmpty
                          ? '© OpenStreetMap'
                          : '© Mapbox © OpenStreetMap',
                      style: TextStyle(
                        fontSize: 9,
                        color: context.textSecondaryColor,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  double _markerSize(SupportFlowNode node, double maxNode) {
    final radius = 4 + 8 * math.sqrt(node.totalWeight / maxNode);
    return radius * 2 + 2;
  }
}

class _MapTool extends StatelessWidget {
  const _MapTool({
    required this.tooltip,
    required this.icon,
    required this.onPressed,
  });

  final String tooltip;
  final IconData icon;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: context.cardColor.withValues(alpha: 0.92),
      shape: const CircleBorder(),
      child: IconButton(
        tooltip: tooltip,
        onPressed: onPressed,
        icon: Icon(icon, size: 18, color: context.navyTextColor),
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.loc});

  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.labelMedium?.copyWith(
          color: context.textSecondaryColor,
        );
    return Wrap(
      spacing: 14,
      runSpacing: 6,
      children: [
        _LegendItem(
          color: _donorColor,
          label: loc.countryDetailInternationalFlowLegendDonor,
          style: style,
        ),
        _LegendItem(
          color: _hostColor,
          label: loc.countryDetailInternationalFlowLegendHost,
          style: style,
        ),
      ],
    );
  }
}

class _LegendItem extends StatelessWidget {
  const _LegendItem({
    required this.color,
    required this.label,
    required this.style,
  });

  final Color color;
  final String label;
  final TextStyle? style;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 6),
        Text(label, style: style),
      ],
    );
  }
}

class _FocusCaption extends StatelessWidget {
  const _FocusCaption({required this.label, required this.onClear});

  final String label;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: publicCardDecoration(context),
      child: Padding(
        padding: const EdgeInsetsDirectional.only(start: 12, end: 4),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
              ),
            ),
            IconButton(
              onPressed: onClear,
              icon: const Icon(Icons.close, size: 18),
            ),
          ],
        ),
      ),
    );
  }
}

class _AreaBars extends StatelessWidget {
  const _AreaBars({
    required this.loc,
    required this.data,
    required this.figures,
  });

  final AppLocalizations loc;
  final SupportFlowData data;
  final List<SupportFlowFigure> figures;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final totals = <String, _AreaTotal>{
      for (final area in data.areas)
        area.code: _AreaTotal(area.label),
    };
    for (final row in figures) {
      final area = totals[row.area];
      if (area == null) continue;
      area.requirement += row.requirement;
      area.expenditure += row.expenditure;
    }
    final rows = totals.values
        .where((area) => area.requirement > 0 || area.expenditure > 0)
        .toList()
      ..sort((a, b) {
        final byRequirement = b.requirement.compareTo(a.requirement);
        if (byRequirement != 0) return byRequirement;
        return b.expenditure.compareTo(a.expenditure);
      });
    final hasRequirement = rows.any((area) => area.requirement > 0);
    final hasExpenditure = rows.any((area) => area.expenditure > 0);
    var maxValue = 1.0;
    for (final area in rows) {
      maxValue = math.max(maxValue, math.max(area.requirement, area.expenditure));
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loc.countryDetailInternationalFlowAreas,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: context.navyTextColor,
          ),
        ),
        const SizedBox(height: 8),
        if (rows.isEmpty)
          Text(
            loc.countryDetailInternationalFlowAreaEmpty,
            style: TextStyle(color: context.textSecondaryColor),
          )
        else ...[
          Wrap(
            spacing: 14,
            runSpacing: 4,
            children: [
              if (hasRequirement)
                _LegendItem(
                  color: _hostColor,
                  label: loc.countryDetailInternationalRequirement,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                ),
              if (hasExpenditure)
                _LegendItem(
                  color: _donorColor,
                  label: loc.countryDetailInternationalExpenditure,
                  style: theme.textTheme.labelMedium?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          for (final area in rows) ...[
            Text(
              area.label,
              style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            if (area.requirement > 0)
              _Meter(
                fraction: area.requirement / maxValue,
                color: _hostColor,
                label: formatSupportAmount(area.requirement),
              ),
            if (area.expenditure > 0) ...[
              const SizedBox(height: 4),
              _Meter(
                fraction: area.expenditure / maxValue,
                color: _donorColor,
                label: formatSupportAmount(area.expenditure),
              ),
            ],
            const SizedBox(height: 10),
          ],
        ],
      ],
    );
  }
}

class _AreaTotal {
  _AreaTotal(this.label);

  final String label;
  double requirement = 0;
  double expenditure = 0;
}

class _FlowKpis extends StatelessWidget {
  const _FlowKpis({
    required this.loc,
    required this.edges,
    required this.figures,
  });

  final AppLocalizations loc;
  final List<SupportFlowEdge> edges;
  final List<SupportFlowFigure> figures;

  @override
  Widget build(BuildContext context) {
    final donors = edges.map((edge) => edge.from).toSet().length;
    final hosts = edges.map((edge) => edge.to).toSet().length;
    final tiles = [
      (loc.countryDetailInternationalFlowDonors, '$donors'),
      (loc.countryDetailInternationalFlowHosts, '$hosts'),
      (
        loc.countryDetailInternationalFlowRequirementTotal,
        formatSupportAmount(sumSupportMetric(figures, 'requirement')),
      ),
      (
        loc.countryDetailInternationalFlowFundingTotal,
        formatSupportAmount(sumSupportMetric(figures, 'funding')),
      ),
      (
        loc.countryDetailInternationalFlowExpenditureTotal,
        formatSupportAmount(sumSupportMetric(figures, 'expenditure')),
      ),
    ];
    return Column(
      children: [
        for (var i = 0; i < tiles.length; i += 2) ...[
          if (i > 0) const SizedBox(height: 10),
          Row(
            children: [
              Expanded(child: KeyFigureTile(label: tiles[i].$1, value: tiles[i].$2)),
              const SizedBox(width: 10),
              if (i + 1 < tiles.length)
                Expanded(
                  child: KeyFigureTile(label: tiles[i + 1].$1, value: tiles[i + 1].$2),
                )
              else
                const Expanded(child: SizedBox.shrink()),
            ],
          ),
        ],
      ],
    );
  }
}

class _FundingRankings extends StatelessWidget {
  const _FundingRankings({
    required this.loc,
    required this.data,
    required this.year,
    required this.pns,
    required this.recipient,
    required this.onPns,
    required this.onRecipient,
  });

  final AppLocalizations loc;
  final SupportFlowData data;
  final int year;
  final String? pns;
  final String? recipient;
  final ValueChanged<String?> onPns;
  final ValueChanged<String?> onRecipient;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final links = [
      for (final link in data.funding)
        if (link.year == year && link.value > 0) link,
    ];
    final sent = _rank(
      recipient == null ? links : links.where((link) => link.to == recipient),
      from: true,
    );
    final received = _rank(
      pns == null ? links : links.where((link) => link.from == pns),
      from: false,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loc.countryDetailInternationalFlowRankings,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: context.navyTextColor,
          ),
        ),
        const SizedBox(height: 10),
        _RankColumn(
          title: loc.countryDetailInternationalFlowSent,
          rows: sent,
          color: _donorColor,
          selected: pns,
          onSelected: onPns,
          empty: loc.countryDetailInternationalFlowBarEmpty,
        ),
        const SizedBox(height: 14),
        _RankColumn(
          title: loc.countryDetailInternationalFlowReceived,
          rows: received,
          color: _hostColor,
          selected: recipient,
          onSelected: onRecipient,
          empty: loc.countryDetailInternationalFlowBarEmpty,
        ),
      ],
    );
  }

  List<_RankRow> _rank(Iterable<SupportFundingLink> links, {required bool from}) {
    final grouped = <String, _RankRow>{};
    for (final link in links) {
      final code = from ? link.from : link.to;
      final name = from ? link.fromName : link.toName;
      final key = code.isNotEmpty ? code : name;
      if (key.isEmpty) continue;
      final current = grouped[key];
      grouped[key] = _RankRow(
        code: code,
        name: name.isEmpty ? (current?.name ?? code) : name,
        value: (current?.value ?? 0) + link.value,
      );
    }
    final rows = grouped.values.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    if (rows.length > 15) return rows.sublist(0, 15);
    return rows;
  }
}

class _RankRow {
  const _RankRow({required this.code, required this.name, required this.value});

  final String code;
  final String name;
  final double value;
}

class _RankColumn extends StatelessWidget {
  const _RankColumn({
    required this.title,
    required this.rows,
    required this.color,
    required this.selected,
    required this.onSelected,
    required this.empty,
  });

  final String title;
  final List<_RankRow> rows;
  final Color color;
  final String? selected;
  final ValueChanged<String?> onSelected;
  final String empty;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final maxValue = rows.fold<double>(1, (max, row) {
      return row.value > max ? row.value : max;
    });
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: theme.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        if (rows.isEmpty)
          Text(empty, style: TextStyle(color: context.textSecondaryColor))
        else
          for (final row in rows)
            _SelectableMeter(
              name: row.name,
              amount: formatSupportAmount(row.value),
              fraction: row.value / maxValue,
              color: color,
              selected: selected != null && selected == row.code,
              onTap: () => onSelected(selected == row.code ? null : row.code),
            ),
      ],
    );
  }
}

class _SelectableMeter extends StatelessWidget {
  const _SelectableMeter({
    required this.name,
    required this.amount,
    required this.fraction,
    required this.color,
    required this.selected,
    required this.onTap,
  });

  final String name;
  final String amount;
  final double fraction;
  final Color color;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 2),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontWeight: selected ? FontWeight.w800 : FontWeight.w600,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    amount,
                    style: TextStyle(fontWeight: FontWeight.w800, color: color),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              _Meter(fraction: fraction, color: color, label: ''),
            ],
          ),
        ),
      ),
    );
  }
}

class _Meter extends StatelessWidget {
  const _Meter({
    required this.fraction,
    required this.color,
    required this.label,
  });

  final double fraction;
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    final width = fraction.clamp(0.0, 1.0);
    return Row(
      children: [
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: SizedBox(
              height: 10,
              child: Stack(
                children: [
                  const Positioned.fill(
                    child: ColoredBox(color: Color(0x14011E41)),
                  ),
                  FractionallySizedBox(
                    widthFactor: width <= 0 ? 0 : math.max(width, 0.04),
                    child: ColoredBox(color: color),
                  ),
                ],
              ),
            ),
          ),
        ),
        if (label.isNotEmpty) ...[
          const SizedBox(width: 8),
          Text(
            label,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ],
    );
  }
}

class _CoverageChart extends StatelessWidget {
  const _CoverageChart({
    required this.loc,
    required this.data,
    required this.year,
    required this.pns,
    required this.recipient,
    required this.onRecipient,
  });

  final AppLocalizations loc;
  final SupportFlowData data;
  final int year;
  final String? pns;
  final String? recipient;
  final ValueChanged<String?> onRecipient;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fundedHosts = <String>{
      if (pns != null)
        for (final link in data.funding)
          if (link.year == year && link.from == pns && link.to.isNotEmpty) link.to,
    };
    final points = [
      for (final point in data.coverage)
        if (point.year == year && point.requirement > 0) point,
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loc.countryDetailInternationalFlowCoverage,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
            color: context.navyTextColor,
          ),
        ),
        const SizedBox(height: 8),
        if (points.isEmpty)
          Text(
            loc.countryDetailInternationalFlowCoverageEmpty,
            style: TextStyle(color: context.textSecondaryColor),
          )
        else
          DecoratedBox(
            decoration: publicCardDecoration(context),
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 12, 12, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    height: 210,
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        return GestureDetector(
                          behavior: HitTestBehavior.opaque,
                          onTapDown: (details) {
                            final hit = _nearestCoverage(
                              details.localPosition,
                              constraints.biggest,
                              points,
                            );
                            if (hit != null) {
                              onRecipient(recipient == hit.iso3 ? null : hit.iso3);
                            }
                          },
                          child: CustomPaint(
                            size: constraints.biggest,
                            painter: _CoveragePainter(
                              points: points,
                              highlight: recipient,
                              fundedHosts: fundedHosts,
                              limitToFunded: pns != null,
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 12,
                    runSpacing: 4,
                    children: [
                      _LegendItem(
                        color: _coverageColor('low'),
                        label: loc.countryDetailInternationalCoverageLow,
                        style: theme.textTheme.labelSmall,
                      ),
                      _LegendItem(
                        color: _coverageColor('medium'),
                        label: loc.countryDetailInternationalCoverageMedium,
                        style: theme.textTheme.labelSmall,
                      ),
                      _LegendItem(
                        color: _coverageColor('high'),
                        label: loc.countryDetailInternationalCoverageHigh,
                        style: theme.textTheme.labelSmall,
                      ),
                      _LegendItem(
                        color: _coverageColor('very high'),
                        label: loc.countryDetailInternationalCoverageVeryHigh,
                        style: theme.textTheme.labelSmall,
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

SupportCoveragePoint? _nearestCoverage(
  Offset tap,
  Size size,
  List<SupportCoveragePoint> points,
) {
  SupportCoveragePoint? best;
  var bestDistance = 18.0;
  for (final point in points) {
    final offset = _coverageOffset(point, size);
    final distance = (offset - tap).distance;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = point;
    }
  }
  return best;
}

Offset _coverageOffset(SupportCoveragePoint point, Size size) {
  const minX = 10000.0;
  const maxX = 100000000.0;
  const left = 28.0;
  const top = 8.0;
  const bottom = 22.0;
  final plotW = math.max(1.0, size.width - left - 8);
  final plotH = math.max(1.0, size.height - top - bottom);
  final requirement = point.requirement.clamp(minX, maxX);
  final t = (math.log(requirement) - math.log(minX)) /
      (math.log(maxX) - math.log(minX));
  final met = (point.met.clamp(0, 100)) / 100;
  return Offset(left + t * plotW, top + (1 - met) * plotH);
}

Color _coverageColor(String raw) {
  final key = raw.toLowerCase().replaceAll('_', ' ').replaceAll('-', ' ');
  if (key.contains('very')) return const Color(0xFF5C1C24);
  if (key.contains('high')) return const Color(0xFF8D2A36);
  if (key.contains('medium')) return const Color(0xFFC44955);
  if (key.contains('low')) return const Color(0xFFE7A0A6);
  return const Color(0xFF8A8F98);
}

class _CoveragePainter extends CustomPainter {
  _CoveragePainter({
    required this.points,
    required this.highlight,
    required this.fundedHosts,
    required this.limitToFunded,
  });

  final List<SupportCoveragePoint> points;
  final String? highlight;
  final Set<String> fundedHosts;
  final bool limitToFunded;

  @override
  void paint(Canvas canvas, Size size) {
    final axis = Paint()
      ..color = const Color(0x33011E41)
      ..strokeWidth = 1;
    const left = 28.0;
    const top = 8.0;
    const bottom = 22.0;
    final plotW = math.max(1.0, size.width - left - 8);
    final plotH = math.max(1.0, size.height - top - bottom);
    canvas.drawLine(const Offset(left, top), Offset(left, top + plotH), axis);
    canvas.drawLine(Offset(left, top + plotH), Offset(left + plotW, top + plotH), axis);

    final label = TextPainter(textDirection: TextDirection.ltr);
    void tick(String text, Offset offset) {
      label.text = TextSpan(
        text: text,
        style: const TextStyle(color: Color(0xFF667085), fontSize: 9),
      );
      label.layout();
      label.paint(canvas, offset);
    }

    tick('100', const Offset(0, top - 4));
    tick('0', Offset(8, top + plotH - 8));
    const ticks = ['10k', '100k', '1M', '10M', '100M'];
    for (var i = 0; i < ticks.length; i++) {
      final x = left + plotW * (i / (ticks.length - 1));
      tick(ticks[i], Offset(x - 10, top + plotH + 4));
    }

    for (final point in points) {
      final dim = limitToFunded && !fundedHosts.contains(point.iso3);
      final selected = highlight != null && highlight == point.iso3;
      final paint = Paint()
        ..color = _coverageColor(point.informClass).withValues(
          alpha: dim ? 0.15 : (selected || highlight == null ? 0.95 : 0.35),
        );
      canvas.drawCircle(_coverageOffset(point, size), selected ? 6 : 4.5, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _CoveragePainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.highlight != highlight ||
        oldDelegate.limitToFunded != limitToFunded ||
        oldDelegate.fundedHosts != fundedHosts;
  }
}

class _FlowStatusBox extends StatelessWidget {
  const _FlowStatusBox.loading()
      : loading = true,
        onRetry = null;

  const _FlowStatusBox.error({required this.onRetry}) : loading = false;

  final bool loading;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const SizedBox(
        height: 160,
        child: Center(
          child: SizedBox(
            width: 28,
            height: 28,
            child: CircularProgressIndicator(strokeWidth: 2.5),
          ),
        ),
      );
    }
    final loc = AppLocalizations.of(context)!;
    return Column(
      children: [
        Text(
          loc.countryDetailInternationalUnavailable,
          textAlign: TextAlign.center,
          style: TextStyle(color: context.textSecondaryColor),
        ),
        TextButton(onPressed: onRetry, child: Text(loc.retry)),
      ],
    );
  }
}

class _MapPointerLock extends StatefulWidget {
  const _MapPointerLock({required this.child});

  final Widget child;

  @override
  State<_MapPointerLock> createState() => _MapPointerLockState();
}

class _MapPointerLockState extends State<_MapPointerLock> {
  int _count = 0;

  void _dispatch() {
    InternationalMapPointerNotification(activePointerCount: _count).dispatch(context);
  }

  @override
  void dispose() {
    final was = _count;
    _count = 0;
    if (was != 0 && context.mounted) {
      InternationalMapPointerNotification(activePointerCount: 0).dispatch(context);
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Listener(
      behavior: HitTestBehavior.deferToChild,
      onPointerDown: (_) {
        _count++;
        _dispatch();
      },
      onPointerUp: (_) {
        _count = (_count - 1).clamp(0, 64);
        _dispatch();
      },
      onPointerCancel: (_) {
        _count = (_count - 1).clamp(0, 64);
        _dispatch();
      },
      child: widget.child,
    );
  }
}
