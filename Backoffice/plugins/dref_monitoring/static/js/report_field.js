/*
 * DREF operational report field.
 * Reads the server-rendered period matrix and writes one JSON value for the form.
 */

export class DrefOperationalReportField {
    constructor(fieldId) {
        this.fieldId = String(fieldId);
        this.root = null;
        this.hidden = null;
    }

    async mount(container) {
        const match = container.querySelector(`[data-field-id="${this.fieldId}"]`);
        this.root = match || container;
        this.hidden = this.root.querySelector("input.dref-report-value");
        this.write();
    }

    serialize() {
        this.write();
    }

    write() {
        if (!this.root || !this.hidden) {
            return;
        }
        const activities = {};
        this.root.querySelectorAll("[data-activity-id]").forEach((block) => {
            const id = block.getAttribute("data-activity-id");
            const row = {};
            block.querySelectorAll("[data-part]").forEach((el) => {
                if (el.hasAttribute("data-indicator-id")) {
                    return;
                }
                row[el.getAttribute("data-part")] = el.value;
            });
            activities[id] = row;
        });
        const indicators = {};
        this.root.querySelectorAll("[data-indicator-id]").forEach((el) => {
            indicators[el.getAttribute("data-indicator-id")] = { actual: el.value };
        });
        const narrative = this.root.querySelector("[data-part='narrative']");
        this.hidden.value = JSON.stringify({
            narrative: narrative ? narrative.value : "",
            activities,
            indicators,
        });
    }
}
