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
        this.bind();
        if (this.root) {
            this.root.querySelectorAll("[data-activity-id]").forEach((block) => this.applyDisaggregation(block));
        }
        this.paintPercentLimits();
        this.write();
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
        this.root.addEventListener("input", (event) => {
            const target = event.target;
            const isPercent = target && target.matches && target.matches(
                "[data-part='pct_women'], [data-part='pct_men'], [data-part='pct_girls'], [data-part='pct_boys']"
            );
            if (!this.problems().length) {
                this.clear();
            }
            if (isPercent) {
                this.paintPercentLimits(target);
            }
        });
        this.root.addEventListener("change", (event) => {
            const box = event.target.closest('[data-part="disaggregation_na"]');
            if (!box) {
                return;
            }
            const block = box.closest("[data-activity-id]");
            if (block) {
                this.applyDisaggregation(block);
                this.paintPercentLimits();
            }
        });
    }

    applyDisaggregation(block) {
        const skipped = block.querySelector('[data-part="disaggregation_na"]');
        const unavailable = Boolean(skipped && skipped.checked);
        const locked = Boolean(skipped && skipped.disabled);
        block.querySelectorAll(".dref-disagg-part").forEach((slot) => {
            slot.classList.toggle("is-unavailable", unavailable);
            const input = slot.querySelector("input");
            if (!input) {
                return;
            }
            if (unavailable) {
                input.value = "";
            }
            input.disabled = unavailable || locked;
        });
        const reason = block.querySelector(".dref-disagg-reason");
        if (reason) {
            reason.hidden = !unavailable;
        }
        const area = block.querySelector('[data-part="disaggregation_reason"]');
        if (!area) {
            return;
        }
        area.required = unavailable && !locked;
        if (!unavailable) {
            area.value = "";
        }
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
                const reason = block.querySelector('[data-part="disaggregation_reason"]');
                if (reason && !String(reason.value || "").trim()) {
                    found.push({
                        field: reason,
                        title,
                        message: this.message("data-msg-disagg", "Explain why this data is not available."),
                    });
                }
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

    paintPercentLimits(edited) {
        if (!this.root) {
            return;
        }
        const eachMessage = this.message("data-msg-percent-each", "A percentage cannot be more than 100.");
        const sumMessage = this.message("data-msg-percent-sum", "The percentages together cannot be more than 100.");
        this.root.querySelectorAll("[data-activity-id]").forEach((block) => {
            const parts = ["pct_women", "pct_men", "pct_girls", "pct_boys"].map((part) => (
                block.querySelector(`[data-part="${part}"]`)
            ));
            if (parts.some((field) => !field)) {
                return;
            }
            parts.forEach((field) => {
                field.classList.remove("dref-percent-invalid");
                field.setCustomValidity("");
                field.removeAttribute("aria-invalid");
            });
            let note = block.querySelector("[data-dref-percent-error]");
            const skipped = block.querySelector('[data-part="disaggregation_na"]');
            if (skipped && skipped.checked) {
                if (note) note.remove();
                block.removeAttribute("data-dref-percent-alert");
                return;
            }
            const active = parts.filter((field) => !field.disabled);
            let over = null;
            let sum = 0;
            let any = false;
            active.forEach((field) => {
                const value = this.number(field.value);
                if (value === null) return;
                any = true;
                sum += value;
                if (value > 100 && !over) over = field;
            });
            let message = "";
            let field = null;
            let marked = [];
            if (over) {
                message = eachMessage;
                field = over;
                marked = active.filter((item) => {
                    const value = this.number(item.value);
                    return value !== null && value > 100;
                });
            } else if (any && sum > 100 + 1e-9) {
                message = sumMessage;
                field = active.includes(edited) ? edited : active.find((item) => this.number(item.value) !== null);
                marked = active.filter((item) => this.number(item.value) !== null);
            }
            if (!message || !field) {
                if (note) note.remove();
                block.removeAttribute("data-dref-percent-alert");
                return;
            }
            if (!marked.includes(field)) marked.push(field);
            marked.forEach((item) => {
                item.classList.add("dref-percent-invalid");
                item.setAttribute("aria-invalid", "true");
            });
            field.setCustomValidity(message);
            if (!note) {
                note = document.createElement("p");
                note.className = "dref-percent-error";
                note.setAttribute("data-dref-percent-error", "");
                note.setAttribute("role", "alert");
                const grid = block.querySelector(".dref-disagg-part");
                const row = grid && grid.parentElement;
                if (row) row.insertAdjacentElement("afterend", note);
                else block.appendChild(note);
            }
            note.hidden = false;
            note.textContent = message;
            if (!edited || !block.contains(edited)) return;
            const key = `${field.getAttribute("data-part") || ""}\n${message}`;
            if (block.getAttribute("data-dref-percent-alert") === key) return;
            block.setAttribute("data-dref-percent-alert", key);
            window.setTimeout(() => {
                if (!field.isConnected || field.validationMessage !== message) return;
                field.reportValidity();
            }, 0);
        });
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
        this.root.querySelectorAll(".dref-invalid, .dref-percent-invalid").forEach((field) => {
            field.classList.remove("dref-invalid", "dref-percent-invalid");
            field.style.borderColor = "";
            field.removeAttribute("aria-invalid");
            if (field.setCustomValidity) field.setCustomValidity("");
        });
        this.root.querySelectorAll("[data-dref-report-error], [data-dref-percent-error]").forEach((note) => note.remove());
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
            /cannot be negative|percentage split|reached total|not available/i.test(alert.textContent || "")
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
