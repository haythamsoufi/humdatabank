/* UPR Analysis — turns a view "chart" (plugins/upr/analysis_spec.py) into
 * ApexCharts options. Pure: no DOM and no globals beyond UprAnalysis.format, so
 * the tab, a browser presentation or a chart-to-image export all draw the same
 * chart from the same description. */
(function (global) {
    'use strict';

    var root = global.UprAnalysis = global.UprAnalysis || {};

    var AXIS_TITLE_STYLE = { fontSize: '11px', color: '#6b7280' };
    var MARKER_SIZE = 4;
    var DASH = 5;

    function formatters() {
        return root.format;
    }

    function uniqueAxisIds(series) {
        var ids = [];
        series.forEach(function (s) {
            if (ids.indexOf(s.axis) === -1) ids.push(s.axis);
        });
        return ids;
    }

    function axisOptions(spec, axisId, firstSeriesName) {
        var axis = (spec.axes || {})[axisId] || {};
        var out = {
            seriesName: firstSeriesName,
            labels: { formatter: formatters().formatter(axis.format) }
        };
        if (axis.opposite) out.opposite = true;
        if (axis.min != null) out.min = axis.min;
        if (axis.max != null) out.max = axis.max;
        if (axis.tick_amount != null) out.tickAmount = axis.tick_amount;
        return out;
    }

    // Apex wants one y-axis entry per series: the first series on an axis owns
    // it, the others point at it and stay hidden.
    function yAxes(spec) {
        var series = spec.series || [];
        var ids = uniqueAxisIds(series);
        var owners = {};
        series.forEach(function (s) {
            if (owners[s.axis] == null) owners[s.axis] = s.name;
        });
        if (ids.length <= 1) {
            var single = axisOptions(spec, ids[0], undefined);
            delete single.seriesName;
            return single;
        }
        return series.map(function (s) {
            if (owners[s.axis] === s.name) return axisOptions(spec, s.axis, s.name);
            return { seriesName: owners[s.axis], show: false };
        });
    }

    function kindsOf(series) {
        var kinds = [];
        series.forEach(function (s) {
            if (kinds.indexOf(s.kind) === -1) kinds.push(s.kind);
        });
        return kinds;
    }

    function baseChartType(kinds) {
        if (kinds.length === 1) return kinds[0] === 'column' ? 'bar' : kinds[0];
        return 'line';
    }

    function tooltipFormatter(series) {
        return function (value, opts) {
            var s = series[opts && opts.seriesIndex != null ? opts.seriesIndex : 0] || {};
            return formatters().format(value, s.format);
        };
    }

    /** ApexCharts options for one view chart. */
    function buildOptions(spec) {
        var series = spec.series || [];
        var kinds = kindsOf(series);
        var options = {
            chart: { type: baseChartType(kinds), height: spec.height || 300 },
            colors: series.map(function (s) { return s.color; }),
            series: series.map(function (s) {
                var item = { name: s.name, data: s.data };
                if (kinds.length > 1) item.type = s.kind;
                return item;
            }),
            xaxis: { categories: spec.categories || [] },
            yaxis: yAxes(spec),
            tooltip: { y: { formatter: tooltipFormatter(series) } }
        };

        if (spec.stacked) options.chart.stacked = true;
        // A fixed width lets a chart draw inside a scaled stage (slides) or a
        // fixed-size page (A4 report), where measuring the container is unreliable.
        if (spec.width) options.chart.width = spec.width;

        if (series.some(function (s) { return s.kind === 'column'; })) {
            options.plotOptions = {
                bar: { columnWidth: spec.column_width, borderRadius: spec.border_radius }
            };
        }

        if (series.some(function (s) { return s.kind !== 'column'; })) {
            options.stroke = {
                width: series.map(function (s) { return s.kind === 'column' ? 0 : spec.stroke_width; }),
                curve: spec.curve,
                dashArray: series.map(function (s) { return s.dashed ? DASH : 0; })
            };
            options.markers = {
                size: series.map(function (s) { return s.kind === 'column' ? 0 : MARKER_SIZE; })
            };
        }

        if (spec.gradient && series.some(function (s) { return s.kind === 'area'; })) {
            options.fill = {
                type: 'gradient',
                gradient: {
                    shadeIntensity: spec.gradient[0],
                    opacityFrom: spec.gradient[1],
                    opacityTo: spec.gradient[2]
                }
            };
        }

        if (spec.legend === false) options.legend = { show: false };
        if (spec.data_labels) options.dataLabels = { enabled: true, style: { fontSize: '11px' } };
        if (spec.x_title) options.xaxis.title = { text: spec.x_title, style: AXIS_TITLE_STYLE };
        return options;
    }

    var BASE = {
        chart: {
            fontFamily: 'inherit',
            toolbar: { show: false },
            animations: { enabled: true, easing: 'easeinout', speed: 500 }
        },
        grid: { borderColor: '#eef0f2', strokeDashArray: 3 },
        dataLabels: { enabled: false },
        legend: { position: 'top', horizontalAlign: 'left', fontSize: '12px' },
        tooltip: { shared: true, intersect: false }
    };

    /** Full Apex configuration: house style plus the chart's own options. */
    function withBaseStyle(options) {
        var merged = Object.assign({}, BASE, options);
        merged.chart = Object.assign({}, BASE.chart, options.chart || {});
        merged.tooltip = Object.assign({}, BASE.tooltip, options.tooltip || {});
        return merged;
    }

    /** Draw ``spec`` into ``container``; returns the Apex instance (or null when Apex is missing). */
    function mount(container, spec, settings) {
        var Apex = global.ApexCharts;
        if (!Apex || !container) return null;
        var config = withBaseStyle(buildOptions(spec));
        // Exports draw every chart at once and print them, so skip the entrance animation.
        if (settings && settings.animate === false) config.chart.animations = { enabled: false };
        var chart = new Apex(container, config);
        chart.render();
        return chart;
    }

    /** Mount every ``{host, chart}`` pair a renderer reported; returns the Apex instances. */
    function mountAll(plots, settings) {
        var charts = [];
        (plots || []).forEach(function (plot) {
            var chart = mount(plot.host, plot.chart, settings);
            if (chart) charts.push(chart);
        });
        return charts;
    }

    var FOCUS_COLOR = '#f5333f';

    /**
     * Highlight the chart categories a finding is about (``{categories: [...]}``
     * from the view), replacing any earlier highlight; a falsy ``spec`` clears it.
     */
    function focus(chart, spec) {
        if (!chart || typeof chart.clearAnnotations !== 'function') return;
        chart.clearAnnotations();
        var seen = {};
        ((spec && spec.categories) || []).forEach(function (category) {
            if (seen[category]) return;
            seen[category] = true;
            chart.addXaxisAnnotation({
                x: category,
                borderColor: FOCUS_COLOR,
                borderWidth: 3,
                strokeDashArray: 0,
                opacity: 0.9
            });
        });
    }

    root.charts = { buildOptions: buildOptions, withBaseStyle: withBaseStyle, mount: mount, mountAll: mountAll, focus: focus };
})(typeof window !== 'undefined' ? window : globalThis);
