/* UPR Analysis — export outline. Turns the views the tab has already loaded into
 * one ordered list of blocks that both the presentation (upr-analysis-slides.js)
 * and the A4 report (upr-analysis-report.js) draw. Nothing here knows about
 * charts or layout: a block only points at a view's own KPIs, visuals and notes,
 * so the two outputs can never disagree with the tab or with each other.
 *
 * Block types: cover, section, kpis, visual, table, notes. */
(function (global) {
    'use strict';

    var root = global.UprAnalysis = global.UprAnalysis || {};

    var TRACKS = ['ALL', 'P', 'MYR', 'AR'];

    function hasData(view) {
        return !!(view && view.has_data);
    }

    /**
     * The sections that can be exported right now:
     * ``[{id, label, available}]`` — ``data`` plus one ``track:<code>`` per
     * participation round type.
     */
    function sections(source, ui) {
        ui = ui || {};
        var list = [{ id: 'data', label: ui.section_data || 'Data', available: hasData(source.impact) }];
        TRACKS.forEach(function (track) {
            var view = source.narrative && source.narrative[track];
            var title = (view && view.title) || '';
            var label = ui['track_' + track] || track;
            list.push({
                id: 'track:' + track,
                label: title ? title + ' — ' + label : label,
                available: hasData(view)
            });
        });
        return list;
    }

    function sectionBlocks(id, title, view, options) {
        var blocks = [{ type: 'section', id: id, title: title, lead: view.lead }];
        if (view.kpis && view.kpis.length) blocks.push({ type: 'kpis', section: id, kpis: view.kpis });
        (view.visuals || []).forEach(function (visual) {
            blocks.push({ type: 'visual', section: id, visual: visual });
        });
        if (options.includeTables) {
            var first = true;
            (view.visuals || []).forEach(function (visual) {
                // Gap lists are already spelled out on the card itself.
                if (!visual.table || visual.kind === 'gaps') return;
                blocks.push({ type: 'table', section: id, visual: visual, first: first });
                first = false;
            });
        }
        if ((view.notes && view.notes.length) || (view.warnings && view.warnings.length)) {
            blocks.push({ type: 'notes', section: id, notes: view.notes || [], warnings: view.warnings || [] });
        }
        return blocks;
    }

    /**
     * ``options``: ``{impact, narrative, ui, region, generatedAt, selected,
     * includeTables}`` where ``selected`` is a list of section ids (see
     * ``sections``). Unavailable or unselected sections are skipped. Returns
     * ``[]`` when nothing is left to show.
     */
    function buildOutline(options) {
        var ui = options.ui || {};
        var wanted = options.selected || [];
        var source = { impact: options.impact, narrative: options.narrative };
        var body = [];

        sections(source, ui).forEach(function (entry) {
            if (!entry.available || wanted.indexOf(entry.id) === -1) return;
            if (entry.id === 'data') {
                body = body.concat(sectionBlocks(entry.id, ui.section_data || options.impact.title, options.impact, options));
            } else {
                var track = entry.id.slice('track:'.length);
                body = body.concat(sectionBlocks(entry.id, entry.label, options.narrative[track], options));
            }
        });
        if (!body.length) return [];

        var when = options.generatedAt instanceof Date ? options.generatedAt : new Date();
        var date = when.toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
        var title = (options.impact && options.impact.title) || (options.narrative && options.narrative.ALL && options.narrative.ALL.title) || '';
        var cover = {
            type: 'cover',
            title: title,
            lead: options.impact && options.impact.lead,
            lines: [
                root.format.fill(ui.export_region, { region: options.region || ui.export_all_regions || '' }),
                root.format.fill(ui.export_generated, { date: date })
            ]
        };
        return [cover].concat(body);
    }

    root.pages = { TRACKS: TRACKS, sections: sections, buildOutline: buildOutline };
})(typeof window !== 'undefined' ? window : globalThis);
