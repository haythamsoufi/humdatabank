import 'dart:convert';
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/foundation.dart' show Factory;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import '../config/app_config.dart';
import '../services/webview_service.dart';
import '../utils/theme_extensions.dart';

String _cssHex(Color color) {
  final r = (color.r * 255.0).round().clamp(0, 255);
  final g = (color.g * 255.0).round().clamp(0, 255);
  final b = (color.b * 255.0).round().clamp(0, 255);
  final int rgb = (r << 16) | (g << 8) | b;
  return '#${rgb.toRadixString(16).padLeft(6, '0')}';
}

/// Distinct slice colors: theme-led, slightly softened for a calm chart read.
List<Color> _chartSliceColors(ColorScheme cs) {
  return [
    cs.primary,
    cs.tertiary,
    cs.secondary,
    Color.alphaBlend(cs.primary.withValues(alpha: 0.62), cs.surface),
    Color.alphaBlend(cs.tertiary.withValues(alpha: 0.62), cs.surface),
    Color.alphaBlend(cs.secondary.withValues(alpha: 0.62), cs.surface),
    cs.error,
  ];
}

String _compactAxisLabel(double value) {
  if (!value.isFinite) return '';
  final r = value.roundToDouble();
  if ((value - r).abs() < 1e-6) return '${r.toInt()}';
  if (value.abs() >= 1000) return '${(value / 1000).toStringAsFixed(1)}k';
  return value.toStringAsFixed(1);
}

/// Renders coerced structured payloads (Backoffice chat-immersive parity).
class AiChatStructuredPayloadsColumn extends StatelessWidget {
  final List<Map<String, dynamic>> payloads;

  const AiChatStructuredPayloadsColumn({
    super.key,
    required this.payloads,
  });

  @override
  Widget build(BuildContext context) {
    if (payloads.isEmpty) return const SizedBox.shrink();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final p in payloads)
          Padding(
            padding: const EdgeInsets.only(top: 10),
            child: _StructuredCard(payload: p),
          ),
      ],
    );
  }
}

class _StructuredCard extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _StructuredCard({required this.payload});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final type = (payload['type'] ?? '').toString().toLowerCase();
    final bg =
        theme.isDarkTheme ? cs.surfaceContainerHighest : cs.surfaceContainerLow;

    Widget child;
    switch (type) {
      case 'data_table':
        child = _DataTableView(payload: payload);
        break;
      case 'line':
      case 'linechart':
      case 'timeseries':
        child = _LineChartView(payload: payload);
        break;
      case 'bar':
      case 'barchart':
        child = _BarChartView(payload: payload);
        break;
      case 'pie':
      case 'donut':
        child = _PieChartView(payload: payload);
        break;
      case 'worldmap':
      case 'world_map':
      case 'choropleth':
        child = _WorldMapWebView(spec: payload);
        break;
      default:
        child = Text(
          payload['title']?.toString() ?? 'Visualization',
          style: TextStyle(color: cs.onSurfaceVariant),
        );
    }

    final title = payload['title']?.toString().trim() ?? '';
    final outlineSoft =
        cs.outline.withValues(alpha: theme.isDarkTheme ? 0.38 : 0.22);
    return Container(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: outlineSoft),
      ),
      clipBehavior: Clip.antiAlias,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (title.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Row(
                children: [
                  Icon(
                    Icons.bar_chart_rounded,
                    size: 18,
                    color: context.navyIconColor,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      title,
                      style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                            letterSpacing: -0.2,
                            color: cs.onSurface,
                          ) ??
                          TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 13,
                            letterSpacing: -0.2,
                            color: cs.onSurface,
                          ),
                    ),
                  ),
                ],
              ),
            ),
          child,
        ],
      ),
    );
  }
}

class _DataTableView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _DataTableView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final rows = payload['rows'];
    if (rows is! List || rows.isEmpty) {
      return const Text('No table rows');
    }
    final cs = Theme.of(context).colorScheme;
    final headerColor = cs.surfaceContainerHigh;
    final textStyle =
        TextStyle(fontSize: 11, color: cs.onSurfaceVariant);

    final first = rows.first;
    List<String> columns;
    if (first is Map) {
      columns = first.keys.map((k) => k.toString()).toList();
    } else {
      columns = List.generate((first as List).length, (i) => '$i');
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Table(
        border: TableBorder.all(color: cs.outline, width: 0.5),
        defaultVerticalAlignment: TableCellVerticalAlignment.middle,
        children: [
          TableRow(
            decoration: BoxDecoration(color: headerColor),
            children: columns
                .map(
                  (c) => Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text(c, style: textStyle.copyWith(fontWeight: FontWeight.w600)),
                  ),
                )
                .toList(),
          ),
          ...rows.take(80).map((r) {
            final cells = <Widget>[];
            if (r is Map) {
              for (final c in columns) {
                cells.add(
                  Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text('${r[c] ?? ''}', style: textStyle),
                  ),
                );
              }
            } else if (r is List) {
              for (var i = 0; i < columns.length; i++) {
                cells.add(
                  Padding(
                    padding: const EdgeInsets.all(6),
                    child: Text(i < r.length ? '${r[i]}' : '', style: textStyle),
                  ),
                );
              }
            }
            return TableRow(children: cells);
          }),
        ],
      ),
    );
  }
}

class _LineChartView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _LineChartView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final series = payload['series'];
    if (series is! List || series.isEmpty) return const SizedBox.shrink();

    final spots = <FlSpot>[];
    for (final p in series) {
      if (p is! Map) continue;
      final x = (p['x'] as num?)?.toDouble();
      final y = (p['y'] as num?)?.toDouble();
      if (x == null || y == null) continue;
      spots.add(FlSpot(x, y));
    }
    if (spots.isEmpty) return const SizedBox.shrink();

    final minX = spots.map((s) => s.x).reduce(math.min);
    final maxX = spots.map((s) => s.x).reduce(math.max);
    final minY = spots.map((s) => s.y).reduce(math.min);
    final maxY = spots.map((s) => s.y).reduce(math.max);
    final padY = (maxY - minY).abs() < 1e-6 ? 1.0 : (maxY - minY) * 0.12;
    final padX = (maxX - minX).abs() < 1e-6 ? 0.5 : (maxX - minX) * 0.02;

    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final lineColor = context.linkOnSurfaceColor;
    final muted = cs.onSurfaceVariant.withValues(alpha: 0.85);
    final gridLine = cs.outline.withValues(alpha: theme.isDarkTheme ? 0.22 : 0.14);
    final axisLabelStyle = theme.textTheme.labelSmall?.copyWith(
          fontSize: 10,
          height: 1.1,
          color: muted,
        ) ??
        TextStyle(fontSize: 10, height: 1.1, color: muted);

    return SizedBox(
      height: 208,
      child: Padding(
        padding: const EdgeInsets.only(top: 4, right: 4),
        child: LineChart(
          LineChartData(
            minX: minX - padX,
            maxX: maxX + padX,
            minY: minY - padY,
            maxY: maxY + padY,
            gridData: FlGridData(
              show: true,
              drawVerticalLine: false,
              horizontalInterval: null,
              getDrawingHorizontalLine: (value) =>
                  FlLine(color: gridLine, strokeWidth: 1),
            ),
            titlesData: FlTitlesData(
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 38,
                  interval: null,
                  getTitlesWidget: (value, meta) {
                    if (value < meta.min || value > meta.max) {
                      return const SizedBox.shrink();
                    }
                    return SideTitleWidget(
                      meta: meta,
                      space: 6,
                      child: Text(
                        _compactAxisLabel(value),
                        style: axisLabelStyle,
                      ),
                    );
                  },
                ),
              ),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 26,
                  interval: null,
                  getTitlesWidget: (value, meta) {
                    if (value < meta.min - 1e-6 || value > meta.max + 1e-6) {
                      return const SizedBox.shrink();
                    }
                    return SideTitleWidget(
                      meta: meta,
                      space: 4,
                      child: Text(
                        _compactAxisLabel(value),
                        style: axisLabelStyle,
                      ),
                    );
                  },
                ),
              ),
              topTitles: const AxisTitles(
                sideTitles: SideTitles(showTitles: false),
              ),
              rightTitles: const AxisTitles(
                sideTitles: SideTitles(showTitles: false),
              ),
            ),
            borderData: FlBorderData(show: false),
            lineTouchData: LineTouchData(
              enabled: true,
              handleBuiltInTouches: true,
              touchTooltipData: LineTouchTooltipData(
                tooltipBorderRadius: BorderRadius.circular(8),
                getTooltipColor: (_) =>
                    cs.surfaceContainerHigh.withValues(alpha: 0.96),
                tooltipPadding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                maxContentWidth: 160,
                tooltipBorder: BorderSide(
                  color: cs.outline.withValues(alpha: 0.28),
                ),
                getTooltipItems: (spots) {
                  return spots.map((s) {
                    return LineTooltipItem(
                      '${_compactAxisLabel(s.x)}  ·  ${_compactAxisLabel(s.y)}',
                      axisLabelStyle.copyWith(
                        fontWeight: FontWeight.w500,
                        color: cs.onSurface,
                      ),
                    );
                  }).toList();
                },
              ),
            ),
            lineBarsData: [
              LineChartBarData(
                spots: spots,
                isCurved: true,
                curveSmoothness: 0.28,
                preventCurveOverShooting: true,
                color: lineColor,
                barWidth: 2.5,
                dotData: const FlDotData(show: false),
                belowBarData: BarAreaData(
                  show: true,
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      lineColor.withValues(alpha: 0.22),
                      lineColor.withValues(alpha: 0.02),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _BarChartView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _BarChartView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final cats = payload['categories'];
    if (cats is! List || cats.isEmpty) return const SizedBox.shrink();

    final labels = <String>[];
    final vals = <double>[];
    for (final c in cats) {
      if (c is! Map) continue;
      labels.add((c['label'] ?? '').toString());
      vals.add((c['value'] as num?)?.toDouble() ?? 0);
    }
    if (vals.isEmpty) return const SizedBox.shrink();

    final maxY = vals.reduce(math.max);
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final barColor = cs.primary;
    final muted = cs.onSurfaceVariant.withValues(alpha: 0.88);
    final gridLine = cs.outline.withValues(alpha: theme.isDarkTheme ? 0.2 : 0.12);
    final labelStyle = theme.textTheme.labelSmall?.copyWith(
          fontSize: 10,
          height: 1.15,
          color: muted,
        ) ??
        TextStyle(fontSize: 10, height: 1.15, color: muted);
    final rodWidth = math.max(10.0, math.min(20.0, 220.0 / math.max(vals.length, 1)));

    return SizedBox(
      height: math.min(292.0, 52.0 + cats.length * 30.0),
      child: Padding(
        padding: const EdgeInsets.only(top: 2, right: 2),
        child: BarChart(
          BarChartData(
            alignment: BarChartAlignment.spaceAround,
            groupsSpace: 10,
            maxY: maxY <= 0 ? 1 : maxY * 1.12,
            gridData: FlGridData(
              show: true,
              drawVerticalLine: false,
              getDrawingHorizontalLine: (value) =>
                  FlLine(color: gridLine, strokeWidth: 1),
            ),
            titlesData: FlTitlesData(
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 38,
                  getTitlesWidget: (value, meta) {
                    if (value > meta.max || value < meta.min) {
                      return const SizedBox.shrink();
                    }
                    return SideTitleWidget(
                      meta: meta,
                      space: 4,
                      child: Text(
                        _compactAxisLabel(value),
                        style: labelStyle,
                      ),
                    );
                  },
                ),
              ),
              bottomTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 48,
                  getTitlesWidget: (v, meta) {
                    final i = v.toInt();
                    if (i < 0 || i >= labels.length) {
                      return const SizedBox.shrink();
                    }
                    final raw = labels[i];
                    final short =
                        raw.length > 12 ? '${raw.substring(0, 10)}…' : raw;
                    return SideTitleWidget(
                      meta: meta,
                      space: 6,
                      child: Text(
                        short,
                        maxLines: 2,
                        textAlign: TextAlign.center,
                        overflow: TextOverflow.ellipsis,
                        style: labelStyle,
                      ),
                    );
                  },
                ),
              ),
              topTitles: const AxisTitles(
                sideTitles: SideTitles(showTitles: false),
              ),
              rightTitles: const AxisTitles(
                sideTitles: SideTitles(showTitles: false),
              ),
            ),
            borderData: FlBorderData(show: false),
            barGroups: List.generate(vals.length, (i) {
              return BarChartGroupData(
                x: i,
                barRods: [
                  BarChartRodData(
                    toY: vals[i],
                    width: rodWidth,
                    borderRadius: const BorderRadius.vertical(
                      top: Radius.circular(6),
                    ),
                    gradient: LinearGradient(
                      begin: Alignment.bottomCenter,
                      end: Alignment.topCenter,
                      colors: [
                        Color.alphaBlend(
                          barColor.withValues(alpha: 0.72),
                          cs.surface,
                        ),
                        barColor,
                      ],
                    ),
                  ),
                ],
              );
            }),
          ),
        ),
      ),
    );
  }
}

class _PieChartView extends StatelessWidget {
  final Map<String, dynamic> payload;

  const _PieChartView({required this.payload});

  @override
  Widget build(BuildContext context) {
    final slices = payload['slices'];
    if (slices is! List || slices.length < 2) return const SizedBox.shrink();

    double total = 0;
    final items = <({String label, double value, Color color})>[];
    final palette = _chartSliceColors(Theme.of(context).colorScheme);

    var i = 0;
    for (final s in slices) {
      if (s is! Map) continue;
      final label = (s['label'] ?? '').toString();
      final v = (s['value'] as num?)?.toDouble() ?? 0;
      if (v <= 0) continue;
      total += v;
      items.add((label: label, value: v, color: palette[i % palette.length]));
      i++;
    }
    if (total <= 0 || items.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final legendStyle = theme.textTheme.labelMedium?.copyWith(
          fontSize: 11,
          height: 1.25,
          color: cs.onSurface,
        ) ??
        TextStyle(fontSize: 11, height: 1.25, color: cs.onSurface);
    final legendMuted = legendStyle.copyWith(
      color: cs.onSurfaceVariant.withValues(alpha: 0.9),
      fontWeight: FontWeight.w400,
    );

    return SizedBox(
      height: 228,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            flex: 5,
            child: PieChart(
              PieChartData(
                sectionsSpace: 1,
                centerSpaceRadius: 44,
                sections: [
                  for (final it in items)
                    PieChartSectionData(
                      color: it.color,
                      value: it.value,
                      title: '',
                      radius: 54,
                      borderSide: BorderSide(
                        color: cs.surface.withValues(alpha: 0.4),
                        width: 1,
                      ),
                    ),
                ],
              ),
            ),
          ),
          Expanded(
            flex: 6,
            child: ListView.separated(
              padding: const EdgeInsets.only(left: 4),
              physics: const BouncingScrollPhysics(),
              itemCount: items.length,
              separatorBuilder: (context, index) =>
                  const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final it = items[index];
                final pct = (it.value / total * 100).round();
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      margin: const EdgeInsets.only(top: 4),
                      decoration: BoxDecoration(
                        color: it.color,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            it.label.isEmpty ? '—' : it.label,
                            style: legendStyle,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          Text(
                            '$pct% · ${it.value.toStringAsFixed(it.value < 10 && it.value != it.value.roundToDouble() ? 1 : 0)}',
                            style: legendMuted,
                          ),
                        ],
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _WorldMapWebView extends StatefulWidget {
  final Map<String, dynamic> spec;

  const _WorldMapWebView({required this.spec});

  @override
  State<_WorldMapWebView> createState() => _WorldMapWebViewState();
}

class _WorldMapWebViewState extends State<_WorldMapWebView> {
  String _html(ColorScheme cs) {
    final specJson = jsonEncode(widget.spec);
    final bg = _cssHex(cs.surface);
    final fg = _cssHex(cs.onSurfaceVariant);
    final stroke = _cssHex(cs.outline);
    return '''
<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
html,body{margin:0;padding:0;height:100%;background:$bg;}
#map{height:280px;width:100%;touch-action:none;}
.info{font:12px/1.35 system-ui;padding:6px 8px;color:$fg;}
</style>
</head><body>
<div class="info" id="t"></div>
<div id="map"></div>
<script>
const spec = $specJson;
document.getElementById('t').textContent = (spec.metric || 'value') + ' — ' + (spec.countries||[]).length + ' countries';
const valueByIso = {};
(spec.countries||[]).forEach(function(c){
  if (c && c.iso3) valueByIso[String(c.iso3).toUpperCase()] = Number(c.value);
});
const vals = Object.values(valueByIso).filter(function(v){return isFinite(v);});
const vmin = vals.length ? Math.min.apply(null, vals) : 0;
const vmax = vals.length ? Math.max.apply(null, vals) : 1;
function colorFor(v){
  if (!isFinite(v)) return '#94a3b8';
  const t = vmax > vmin ? (v - vmin) / (vmax - vmin) : 0.5;
  const r = Math.round(30 + 180 * t);
  const g = Math.round(100 + 80 * (1-t));
  const b = Math.round(180 - 100 * t);
  return 'rgb('+r+','+g+','+b+')';
}
const map = L.map('map', { scrollWheelZoom: false, zoomControl: true, worldCopyJump: true }).setView([20, 0], 2);
window.__humdbMap = map;
window.__humdbInvalidateMap = function(){
  try { map.invalidateSize(true); } catch (e) {}
};
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 8,
  attribution: '&copy; OpenStreetMap'
}).addTo(map);
function loadWorldGeoJson(){
  var urls = [
    'https://cdn.jsdelivr.net/gh/datasets/geo-countries@master/data/countries.geojson',
    'https://cdn.jsdelivr.net/gh/holtzy/D3-graph-gallery@master/DATA/world.geojson'
  ];
  function tryFetch(i){
    if (i >= urls.length){
      document.getElementById('t').textContent = 'Map data unavailable (network)';
      return;
    }
    fetch(urls[i]).then(function(r){
      if (!r.ok) throw new Error('geojson');
      return r.json();
    }).then(function(geo){
    L.geoJSON(geo, {
      style: function(feature){
        var p = feature.properties || {};
        var iso = (p.ISO_A3 || p.iso_a3 || p.ISO_A3_EH || '').toString().toUpperCase();
        var v = valueByIso[iso];
        return {
          fillColor: colorFor(v),
          weight: 0.5,
          color: '$stroke',
          fillOpacity: 0.75
        };
      }
    }).addTo(map);
    setTimeout(function(){ window.__humdbInvalidateMap(); }, 100);
    setTimeout(function(){ window.__humdbInvalidateMap(); }, 400);
    }).catch(function(){ tryFetch(i + 1); });
  }
  tryFetch(0);
}
loadWorldGeoJson();
</script>
</body></html>
''';
  }

  /// HTTPS base avoids Android mixed-content blocking when API is http:// during dev.
  WebUri _initialBaseUrl() {
    try {
      final u = Uri.parse(AppConfig.baseApiUrl);
      if (u.scheme == 'https' && u.host.isNotEmpty) {
        return WebUri(AppConfig.baseApiUrl);
      }
    } catch (_) {}
    return WebUri('https://cdn.jsdelivr.net/');
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final settings = WebViewService.defaultSettings(allowMixedContent: true);
    return SizedBox(
      height: 308,
      child: InAppWebView(
        initialSettings: settings,
        gestureRecognizers: <Factory<OneSequenceGestureRecognizer>>{
          Factory<OneSequenceGestureRecognizer>(() => VerticalDragGestureRecognizer()),
          Factory<OneSequenceGestureRecognizer>(() => HorizontalDragGestureRecognizer()),
        }.toSet(),
        initialData: InAppWebViewInitialData(
          data: _html(cs),
          baseUrl: _initialBaseUrl(),
        ),
        onLoadStop: (controller, url) async {
          await controller.evaluateJavascript(
            source: 'try{window.__humdbInvalidateMap&&window.__humdbInvalidateMap();}catch(e){}',
          );
        },
      ),
    );
  }
}
