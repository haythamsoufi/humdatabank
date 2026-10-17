/*
 * NSD logframe field (plugin nsd_report_forms, field type "nsd_logframe").
 *
 * One field holds the whole outcome / output / activity / indicator structure of an
 * initiative, in the same shape MOMO stores in output_review_data:
 *
 *   [{ category, definition, planned_budget, status, comments,
 *      indicators: [{ name, baseline, target, actual_target }],
 *      outputs: [{ name, planned_budget, status, comments,
 *                  indicators: [...],
 *                  activities: [{ name, planned_budget, actual_budget }] }] }]
 *
 * mode "plan"   (project profile): the structure itself is editable.
 * mode "report" (final report)    : the structure is read-only (carried forward from the
 *                                   profile); assessments, actuals and comments are editable.
 *
 * The value is written to the hidden input field_value[<id>] as JSON on every change.
 */
const STATUS = {
    outcome: [['target_reached', 'Achieved', 'green'], ['target_partially_achieved', 'Partially achieved', 'amber'],
              ['target_less_than_50', 'Not achieved', 'red']],
    output: [['target_reached', 'Target reached', 'green'], ['target_partially_achieved', 'Partially achieved', 'amber'],
             ['target_less_than_50', 'Not reached', 'red']],
};

const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => { const n = parseFloat(String(v == null ? '' : v).replace(/,/g, '')); return Number.isFinite(n) ? n : null; };
const fmt = (n) => (n == null ? '' : Math.round(n).toLocaleString('en-US'));
const pct = (a, p) => (a == null || !p ? '' : Math.round((a / p) * 100) + '%');

export class NsdLogframeField {
    constructor(fieldId) {
        this.fieldId = String(fieldId);
        this.data = [];
        this.mode = 'report';
        this.canEdit = true;
    }

    async mount(container, context = {}) {
        if (container.__nsdMounted) return; // mounted early by nsd-report-forms.js
        container.__nsdMounted = true;
        // Render into our own wrapper and keep it in the page: the core re-creates the
        // field when the element carrying data-field-id disappears.
        let root = container.querySelector(`div[data-field-id="${this.fieldId}"]`);
        if (!root) {
            root = document.createElement('div');
            root.setAttribute('data-field-id', this.fieldId);
            container.appendChild(root);
        }
        this.container = root;
        this.canEdit = context.canEdit !== false;
        this.mode = (context.pluginConfig && context.pluginConfig.mode) === 'plan' ? 'plan' : 'report';
        this.data = this.extract(context.existingData);

        root.classList.add('nsdlf');
        root.addEventListener('input', (e) => this.onInput(e));
        root.addEventListener('change', (e) => this.onInput(e));
        root.addEventListener('click', (e) => this.onClick(e));
        this.render();
    }

    serialize() { this.write(); }

    // existingData may arrive as the array itself, {value: ...}, or a JSON string at any level
    extract(raw) {
        let v = raw;
        for (let i = 0; i < 4 && v != null; i++) {
            if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { return []; } continue; }
            if (Array.isArray(v)) return v;
            if (typeof v === 'object') {
                if (v.outcomes) { v = v.outcomes; continue; }
                if (v.value !== undefined) { v = v.value; continue; }
                if (v.original !== undefined) { v = v.original; continue; }
                return [];
            }
            return [];
        }
        return Array.isArray(v) ? v : [];
    }

    write() {
        let input = this.container.querySelector('input.nsdlf-value');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.className = 'nsdlf-value';
            input.name = `field_value[${this.fieldId}]`;
            this.container.appendChild(input);
        }
        input.value = JSON.stringify(this.data);
    }

    // ---- model helpers --------------------------------------------------------
    at(path) {
        return path.split('.').reduce((o, k) => (o == null ? o : o[k]), this.data);
    }

    setAt(path, value) {
        const keys = path.split('.');
        const last = keys.pop();
        const parent = keys.reduce((o, k) => o[k], this.data);
        parent[last] = value;
    }

    activitySum(output) {
        const vals = (output.activities || []).map((a) => num(a.actual_budget)).filter((n) => n != null);
        return vals.length ? vals.reduce((s, n) => s + n, 0) : null;
    }

    outcomeSum(outcome) {
        const vals = (outcome.outputs || []).map((o) => this.activitySum(o)).filter((n) => n != null);
        return vals.length ? vals.reduce((s, n) => s + n, 0) : null;
    }

    // ---- events ---------------------------------------------------------------
    onInput(e) {
        const el = e.target;
        const path = el.getAttribute && el.getAttribute('data-path');
        if (!path) return;
        let value = el.value;
        if (el.getAttribute('data-num') === '1') value = value === '' ? '' : (num(value) == null ? 0 : num(value));
        this.setAt(path, value);
        this.updateTotals();
        this.write();
    }

    onClick(e) {
        const btn = e.target.closest && e.target.closest('[data-act]');
        const card = e.target.closest && e.target.closest('[data-status-path]');
        if (card && this.canEdit && this.mode === 'report') {
            this.setAt(card.getAttribute('data-status-path'), card.getAttribute('data-status-value'));
            this.write();
            this.updateStatusCards();
            return;
        }
        if (!btn || !this.canEdit) return;
        const act = btn.getAttribute('data-act');
        const path = btn.getAttribute('data-target') || '';
        if (act === 'add-outcome') this.data.push({ definition: '', planned_budget: '', indicators: [], outputs: [] });
        else if (act === 'add-output') this.at(path).outputs.push({ name: '', planned_budget: '', indicators: [], activities: [] });
        else if (act === 'add-activity') this.at(path).activities.push({ name: '', planned_budget: '' });
        else if (act === 'add-indicator') this.at(path).indicators.push({ name: '', baseline: '', target: '' });
        else if (act === 'remove') {
            const keys = path.split('.');
            const idx = parseInt(keys.pop(), 10);
            this.at(keys.join('.')).splice(idx, 1);
        } else if (act === 'prefill') {
            this.data.forEach((o) => (o.outputs || []).forEach((out) => (out.activities || []).forEach((a) => {
                a.actual_budget = a.planned_budget == null ? '' : a.planned_budget;
            })));
        } else return;
        this.write();
        this.render();
    }

    // ---- rendering ------------------------------------------------------------
    field(path, value, { s = false, number = false, area = false, ph = '' } = {}) {
        const editable = this.canEdit && (s ? this.mode === 'plan' : this.mode === 'report');
        if (!editable) {
            const shown = number && value !== '' && value != null ? fmt(num(value)) : value;
            return `<div class="nsdlf-ro">${esc(shown) || '&nbsp;'}</div>`;
        }
        const attrs = `data-path="${esc(path)}" ${number ? 'data-num="1" inputmode="decimal"' : ''} placeholder="${esc(ph)}"`;
        return area ? `<textarea class="nsdlf-in" rows="2" ${attrs}>${esc(value)}</textarea>`
                    : `<input class="nsdlf-in" type="text" ${attrs} value="${esc(value)}">`;
    }

    statusCards(kind, path, current) {
        if (this.mode !== 'report') return '';
        const cards = STATUS[kind].map(([val, label, color]) =>
            `<label class="nsd-tl-card nsd-tl-card--${color}${current === val ? ' is-selected' : ''}" data-status-path="${esc(path)}" data-status-value="${val}">
                <input type="radio" ${current === val ? 'checked' : ''} ${this.canEdit ? '' : 'disabled'}><span>${label}</span></label>`).join('');
        return `<div class="nsdlf-status"><span class="nsdlf-status-label">Assessment:</span><div class="nsd-tl-group">${cards}</div></div>`;
    }

    updateStatusCards() {
        this.container.querySelectorAll('[data-status-path]').forEach((card) => {
            const on = this.at(card.getAttribute('data-status-path')) === card.getAttribute('data-status-value');
            card.classList.toggle('is-selected', on);
            const r = card.querySelector('input');
            if (r) r.checked = on;
        });
    }

    indicators(list, base, label) {
        const plan = this.mode === 'plan';
        if (!list.length && !plan) return '';
        const rows = list.map((ind, i) => `<tr>
            <td>${this.field(`${base}.indicators.${i}.name`, ind.name, { s: true, area: true })}</td>
            <td>${this.field(`${base}.indicators.${i}.baseline`, ind.baseline, { s: true })}</td>
            <td>${this.field(`${base}.indicators.${i}.target`, ind.target, { s: true })}</td>
            ${plan ? `<td><button type="button" class="nsdlf-x" data-act="remove" data-target="${base}.indicators.${i}">&times;</button></td>`
                   : `<td>${this.field(`${base}.indicators.${i}.actual_target`, ind.actual_target, { ph: 'Enter actual' })}</td>`}
        </tr>`).join('');
        return `<table class="nsdlf-table"><thead><tr><th style="width:38%">${label} Indicator</th><th>Baseline</th><th>Target</th>
            <th>${plan ? '' : 'Actual value'}</th></tr></thead><tbody>${rows}</tbody></table>
            ${plan ? `<button type="button" class="nsdlf-add" data-act="add-indicator" data-target="${base}">+ Add indicator</button>` : ''}`;
    }

    outputHtml(oc, oi, out, ui) {
        const base = `${oi}.outputs.${ui}`;
        const plan = this.mode === 'plan';
        const acts = (out.activities || []).map((a, ai) => `<tr>
            <td>${this.field(`${base}.activities.${ai}.name`, a.name, { s: true, area: true })}</td>
            <td>${this.field(`${base}.activities.${ai}.planned_budget`, a.planned_budget, { s: true, number: true })}</td>
            ${plan ? `<td colspan="2"><button type="button" class="nsdlf-x" data-act="remove" data-target="${base}.activities.${ai}">&times;</button></td>`
                   : `<td>${this.field(`${base}.activities.${ai}.actual_budget`, a.actual_budget, { number: true })}</td>
                      <td class="nsdlf-pct" data-pct-act="${base}.activities.${ai}"></td>`}
        </tr>`).join('');
        const actTable = (out.activities || []).length || plan ? `<table class="nsdlf-table"><thead><tr>
            <th style="width:50%">Activity</th><th>Planned budget</th>${plan ? '<th colspan="2"></th>' : '<th>Actual amount spent</th><th>%</th>'}
            </tr></thead><tbody>${acts}</tbody></table>
            ${plan ? `<button type="button" class="nsdlf-add" data-act="add-activity" data-target="${base}">+ Add activity</button>` : ''}` : '';
        return `<div class="nsdlf-card nsdlf-output">
            <div class="nsdlf-head"><strong>Outcome ${oi + 1} - Output ${ui + 1}</strong>
                ${plan ? `<button type="button" class="nsdlf-x" data-act="remove" data-target="${oi}.outputs.${ui}">&times;</button>` : ''}</div>
            ${this.statusCards('output', `${base}.status`, out.status)}
            <div class="nsdlf-grid">
                <div class="nsdlf-c6"><label>Output</label>${this.field(`${base}.name`, out.name, { s: true, area: true })}</div>
                <div class="nsdlf-c2"><label>Planned budget</label>${this.field(`${base}.planned_budget`, out.planned_budget, { s: true, number: true })}</div>
                ${plan ? '' : `<div class="nsdlf-c2"><label>Actual amount spent</label><div class="nsdlf-ro nsdlf-sum" data-sum-out="${base}"></div></div>
                <div class="nsdlf-c2"><label>%</label><div class="nsdlf-ro nsdlf-pct" data-pct-out="${base}"></div></div>`}
            </div>
            ${this.indicators(out.indicators || [], base, 'Output')}
            ${actTable}
            ${plan ? '' : `<label class="nsdlf-lbl">Optional comments for output ${ui + 1}</label>${this.field(`${base}.comments`, out.comments, { area: true })}`}
        </div>`;
    }

    outcomeHtml(oc, oi) {
        const plan = this.mode === 'plan';
        const outs = (oc.outputs || []).map((o, ui) => this.outputHtml(oc, oi, o, ui)).join('');
        return `<div class="nsdlf-card nsdlf-outcome">
            <div class="nsdlf-head"><strong>Outcome ${oi + 1}</strong>
                ${plan ? `<button type="button" class="nsdlf-x" data-act="remove" data-target="${oi}">&times;</button>` : ''}</div>
            ${this.statusCards('outcome', `${oi}.status`, oc.status)}
            <div class="nsdlf-grid">
                <div class="nsdlf-c6"><label>Outcome</label>${this.field(`${oi}.definition`, oc.definition, { s: true, area: true })}</div>
                <div class="nsdlf-c2"><label>Planned budget</label>${this.field(`${oi}.planned_budget`, oc.planned_budget, { s: true, number: true })}</div>
                ${plan ? '' : `<div class="nsdlf-c2"><label>Actual budget (sum)</label><div class="nsdlf-ro nsdlf-sum" data-sum-oc="${oi}"></div></div>
                <div class="nsdlf-c2"><label>%</label><div class="nsdlf-ro nsdlf-pct" data-pct-oc="${oi}"></div></div>`}
            </div>
            ${this.indicators(oc.indicators || [], `${oi}`, 'Outcome')}
            ${plan ? '' : `<label class="nsdlf-lbl">Optional comments for outcome ${oi + 1}</label>${this.field(`${oi}.comments`, oc.comments, { area: true })}`}
            <div class="nsdlf-outputs">${outs}</div>
            ${plan ? `<button type="button" class="nsdlf-add" data-act="add-output" data-target="${oi}">+ Add output</button>` : ''}
        </div>`;
    }

    render() {
        const plan = this.mode === 'plan';
        let html = '';
        if (!this.data.length && !plan) {
            html = '<div class="nsdlf-empty">No outcomes found for this initiative. They are defined in the project profile.</div>';
        } else {
            html = this.data.map((o, i) => this.outcomeHtml(o, i)).join('');
        }
        if (plan && this.canEdit) html += '<button type="button" class="nsdlf-add" data-act="add-outcome">+ Add outcome</button>';
        if (!plan && this.canEdit && this.data.length) {
            html = '<div class="nsdlf-tools"><button type="button" class="nsdlf-add" data-act="prefill" ' +
                   'title="Fill every activity actual amount spent with its planned budget">= Prefill actual amount spent from planned budget</button></div>' + html;
        }
        const keep = this.container.querySelector('input.nsdlf-value');
        this.container.innerHTML = html;
        if (keep) this.container.appendChild(keep);
        this.write();
        this.updateTotals();
    }

    updateTotals() {
        if (this.mode === 'plan') return;
        const set = (sel, text) => this.container.querySelectorAll(sel).forEach((el) => { el.textContent = text; });
        this.data.forEach((oc, oi) => {
            (oc.outputs || []).forEach((out, ui) => {
                const base = `${oi}.outputs.${ui}`;
                const sum = this.activitySum(out);
                set(`[data-sum-out="${base}"]`, fmt(sum));
                set(`[data-pct-out="${base}"]`, pct(sum, num(out.planned_budget)));
                (out.activities || []).forEach((a, ai) => set(`[data-pct-act="${base}.activities.${ai}"]`, pct(num(a.actual_budget), num(a.planned_budget))));
            });
            const sum = this.outcomeSum(oc);
            set(`[data-sum-oc="${oi}"]`, fmt(sum));
            set(`[data-pct-oc="${oi}"]`, pct(sum, num(oc.planned_budget)));
        });
    }
}

export default NsdLogframeField;
