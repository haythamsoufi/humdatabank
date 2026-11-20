/*
 * DREF operational report field.
 * Reads the server-rendered period matrix and writes one JSON value for the form.
 * A split that does not add up, a split without a reached total, or a negative
 * expenditure is stopped here so the assignment page does not reload and drop the update.
 */

export class DrefOperationalReportField {
    constructor(fieldId) {
        this.fieldId = String(fieldId);
        this.root = null;
        this.hidden = null;
    }

    async mount(container) {
        const match = container.querySelector(`.dref-report-field[data-field-id="${this.fieldId}"]`)
            || container.querySelector(".dref-report-field");
        this.root = match || container;
        this.hidden = this.root.querySelector("input.dref-report-value");
        this.restoreIfRejected();
        this.write();
        this.bind();
    }

    serialize() {
        this.write();
    }

    message(name, fallback) {
        return (this.root && this.root.getAttribute(name)) || fallback;
    }

    draftKey() {
        return `dref-report-draft:${window.location.pathname}:${this.fieldId}`;
    }

    bind() {
        const form = this.root && this.root.closest("form");
        if (!form || form.dataset.drefReportGuard === this.fieldId) {
            return;
        }
        form.dataset.drefReportGuard = this.fieldId;
        form.addEventListener("submit", (event) => {
            const problems = this.problems();
            if (problems.length) {
                event.preventDefault();
                event.stopPropagation();
                this.show(problems);
                return;
            }
            this.clear();
            this.remember();
        }, true);
        this.root.addEventListener("input", () => {
            if (!this.problems().length) {
                this.clear();
            }
        });
    }

    number(value) {
        const text = String(value ?? "").replace(/,/g, "").trim();
        if (!text) {
            return null;
        }
        const parsed = Number(text);
        return Number.isFinite(parsed) ? parsed : null;
    }

    problems() {
        const found = [];
        if (!this.root) {
            return found;
        }
        const splitMessage = this.message("data-msg-split", "The percentage split must add up to 100.");
        const reachedMessage = this.message("data-msg-reached", "Enter the reached total before the percentage split.");
        const expenditureMessage = this.message("data-msg-expenditure", "Expenditure cannot be negative.");
        this.root.querySelectorAll("[data-activity-id]").forEach((block) => {
            const titleNode = block.querySelector("p");
            const title = titleNode ? titleNode.textContent.trim() : "";
            const expenditure = block.querySelector('[data-part="expenditure"]');
            if (expenditure && !expenditure.disabled && this.number(expenditure.value) < 0) {
                found.push({ field: expenditure, title, message: expenditureMessage });
            }
            const skipped = block.querySelector('[data-part="disaggregation_na"]');
            if (skipped && skipped.checked) {
                return;
            }
            const parts = ["pct_women", "pct_men", "pct_girls", "pct_boys"].map((part) => (
                block.querySelector(`[data-part="${part}"]`)
            ));
            if (parts.some((field) => !field)) {
                return;
            }
            const values = parts.map((field) => this.number(field.value));
            if (values.every((value) => value === null)) {
                return;
            }
            const reached = block.querySelector('[data-part="reached"]');
            if (values.some((value) => value === null) || values.reduce((sum, value) => sum + Math.trunc(value), 0) !== 100) {
                found.push({ field: parts.find((field) => field) , title, message: splitMessage });
            }
            if (reached && !reached.disabled && this.number(reached.value) === null) {
                found.push({ field: reached, title, message: reachedMessage });
            }
        });
        return found;
    }

    show(problems) {
        this.clear();
        problems.forEach((item) => {
            item.field.classList.add("dref-invalid");
            item.field.style.borderColor = "#b91c1c";
            const block = item.field.closest("[data-activity-id]") || item.field.parentElement;
            if (!block) {
                return;
            }
            let note = block.querySelector("[data-dref-report-error]");
            const line = item.title ? `${item.title}: ${item.message}` : item.message;
            if (!note) {
                note = document.createElement("p");
                note.setAttribute("data-dref-report-error", "");
                note.setAttribute("role", "alert");
                note.style.color = "#b91c1c";
                note.style.fontSize = "0.875rem";
                note.style.marginTop = "0.5rem";
                note.textContent = line;
                block.appendChild(note);
                return;
            }
            if (!note.textContent.includes(item.message)) {
                note.textContent = `${note.textContent} ${line}`;
            }
        });
        if (problems[0]) {
            problems[0].field.scrollIntoView({ block: "center" });
            problems[0].field.focus();
        }
    }

    clear() {
        if (!this.root) {
            return;
        }
        this.root.querySelectorAll(".dref-invalid").forEach((field) => {
            field.classList.remove("dref-invalid");
            field.style.borderColor = "";
        });
        this.root.querySelectorAll("[data-dref-report-error]").forEach((note) => note.remove());
    }

    snapshot() {
        const activities = {};
        this.root.querySelectorAll("[data-activity-id]").forEach((block) => {
            const id = block.getAttribute("data-activity-id");
            const row = {};
            block.querySelectorAll("[data-part]").forEach((el) => {
                if (el.hasAttribute("data-indicator-id") || el.disabled) {
                    return;
                }
                row[el.getAttribute("data-part")] = el.type === "checkbox" ? (el.checked ? "1" : "") : el.value;
            });
            activities[id] = row;
        });
        const indicators = {};
        this.root.querySelectorAll("[data-indicator-id]").forEach((el) => {
            if (!el.disabled) {
                indicators[el.getAttribute("data-indicator-id")] = el.value;
            }
        });
        const narrative = this.root.querySelector("[data-part='narrative']");
        return {
            narrative: narrative && !narrative.disabled ? narrative.value : "",
            activities,
            indicators,
        };
    }

    remember() {
        try {
            window.sessionStorage.setItem(this.draftKey(), JSON.stringify(this.snapshot()));
        } catch (err) {
            /* A rejected save cannot put this update back. */
        }
    }

    restoreIfRejected() {
        let raw = null;
        try {
            raw = window.sessionStorage.getItem(this.draftKey());
        } catch (err) {
            return;
        }
        const failed = Array.from(document.querySelectorAll(".alert-danger")).some((alert) => (
            /cannot be negative|percentage split|reached total/i.test(alert.textContent || "")
        ));
        if (!failed) {
            try {
                window.sessionStorage.removeItem(this.draftKey());
            } catch (err) {
                /* Nothing stored to clear. */
            }
            return;
        }
        if (!raw) {
            return;
        }
        let saved = null;
        try {
            saved = JSON.parse(raw);
        } catch (err) {
            return;
        }
        const activities = saved.activities || {};
        this.root.querySelectorAll("[data-activity-id]").forEach((block) => {
            const row = activities[block.getAttribute("data-activity-id")] || {};
            block.querySelectorAll("[data-part]").forEach((el) => {
                if (el.disabled || !(el.getAttribute("data-part") in row)) {
                    return;
                }
                if (el.type === "checkbox") {
                    el.checked = row[el.getAttribute("data-part")] === "1";
                } else {
                    el.value = row[el.getAttribute("data-part")];
                }
            });
        });
        const indicators = saved.indicators || {};
        this.root.querySelectorAll("[data-indicator-id]").forEach((el) => {
            const id = el.getAttribute("data-indicator-id");
            if (!el.disabled && id in indicators) {
                el.value = indicators[id];
            }
        });
        const narrative = this.root.querySelector("[data-part='narrative']");
        if (narrative && !narrative.disabled && "narrative" in saved) {
            narrative.value = saved.narrative;
        }
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
                const part = el.getAttribute("data-part");
                row[part] = el.type === "checkbox" ? (el.checked ? "1" : "") : el.value;
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

function bootReportFields() {
    document.querySelectorAll(".dref-report-field").forEach((root) => {
        const container = root.closest(".plugin-field-container");
        if (container && container.pluginInstance && container.pluginInstance.root === root) {
            return;
        }
        const fieldId = root.getAttribute("data-field-id") || "";
        const instance = new DrefOperationalReportField(fieldId);
        if (container) {
            container.pluginInstance = instance;
        }
        instance.mount(container || root);
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bootReportFields);
} else {
    bootReportFields();
}
