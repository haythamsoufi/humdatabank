/*
 * NSD list field (plugin nsd_report_forms, field type "nsd_list").
 *
 * A small "add rows" field that sits in a normal question card, e.g. other partners or
 * new partnerships. Config (plugin_config):
 *   columns:   [{ key, label, type: "text" | "select", options: [...], placeholder }]
 *   add_label: text of the Add button
 * The value is a JSON array of objects, written to the hidden input field_value[<id>].
 */
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export class NsdListField {
    constructor(fieldId) {
        this.fieldId = String(fieldId);
        this.rows = [];
        this.columns = [{ key: 'name', label: 'Name', type: 'text' }];
        this.addLabel = 'Add';
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
        const cfg = context.pluginConfig || {};
        if (Array.isArray(cfg.columns) && cfg.columns.length) this.columns = cfg.columns;
        if (cfg.add_label) this.addLabel = cfg.add_label;
        this.rows = this.extract(context.existingData);

        root.classList.add('nsdli');
        root.addEventListener('input', (e) => this.onInput(e));
        root.addEventListener('change', (e) => this.onInput(e));
        root.addEventListener('click', (e) => this.onClick(e));
        this.render();
    }

    serialize() { this.write(); }

    extract(raw) {
        let v = raw;
        for (let i = 0; i < 4 && v != null; i++) {
            if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { return []; } continue; }
            if (Array.isArray(v)) return v.filter((r) => r && typeof r === 'object');
            if (typeof v === 'object') {
                if (v.value !== undefined) { v = v.value; continue; }
                if (v.original !== undefined) { v = v.original; continue; }
                return [];
            }
            return [];
        }
        return [];
    }

    write() {
        let input = this.container.querySelector('input.nsdli-value');
        if (!input) {
            input = document.createElement('input');
            input.type = 'hidden';
            input.className = 'nsdli-value';
            input.name = `field_value[${this.fieldId}]`;
            this.container.appendChild(input);
        }
        input.value = JSON.stringify(this.rows.filter((r) => this.columns.some((c) => String(r[c.key] || '').trim())));
    }

    onInput(e) {
        const el = e.target;
        const row = el.getAttribute && el.getAttribute('data-row');
        const key = el.getAttribute && el.getAttribute('data-key');
        if (row == null || !key) return;
        this.rows[parseInt(row, 10)][key] = el.value;
        this.write();
    }

    onClick(e) {
        const btn = e.target.closest && e.target.closest('[data-act]');
        if (!btn || !this.canEdit) return;
        e.preventDefault();
        if (btn.getAttribute('data-act') === 'add') {
            this.rows.push({});
        } else if (btn.getAttribute('data-act') === 'remove') {
            this.rows.splice(parseInt(btn.getAttribute('data-row'), 10), 1);
        }
        this.write();
        this.render();
        const last = this.container.querySelector('.nsdli-row:last-of-type input, .nsdli-row:last-of-type select');
        if (btn.getAttribute('data-act') === 'add' && last) last.focus();
    }

    cell(col, r, i) {
        const value = r[col.key] == null ? '' : r[col.key];
        const attrs = `data-row="${i}" data-key="${esc(col.key)}" ${this.canEdit ? '' : 'disabled'}`;
        if (col.type === 'select') {
            const opts = ['<option value="">Select...</option>'].concat((col.options || []).map((o) =>
                `<option value="${esc(o)}"${o === value ? ' selected' : ''}>${esc(o)}</option>`)).join('');
            return `<div class="nsdli-cell"><label>${esc(col.label)}</label><select class="nsdli-in" ${attrs}>${opts}</select></div>`;
        }
        return `<div class="nsdli-cell"><label>${esc(col.label)}</label>
            <input class="nsdli-in" type="text" ${attrs} value="${esc(value)}" placeholder="${esc(col.placeholder || '')}"></div>`;
    }

    render() {
        const rows = this.rows.map((r, i) => `<div class="nsdli-row">
            ${this.columns.map((c) => this.cell(c, r, i)).join('')}
            ${this.canEdit ? `<button type="button" class="nsdli-x" data-act="remove" data-row="${i}" title="Remove">&times;</button>` : ''}
        </div>`).join('');
        const keep = this.container.querySelector('input.nsdli-value');
        this.container.innerHTML = rows +
            (this.canEdit ? `<button type="button" class="nsdli-add" data-act="add">+ ${esc(this.addLabel)}</button>` : '');
        if (keep) this.container.appendChild(keep);
        this.write();
    }
}

export default NsdListField;
