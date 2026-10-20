/**
 * Read-only Swiss-franc line for FDRS amounts entered in a local currency.
 * The companion figure is posted on the hidden form item. Income-source cells
 * are converted again on save.
 */
(function () {
    var context = null;

    function aesId() {
        var input = document.querySelector('input[name="assignment_entity_status_id"]');
        return input ? String(input.value || "").trim() : "";
    }

    function currencyCode() {
        if (!context || !context.currency_item_id) return "";
        var field = document.querySelector('[name="field_value[' + context.currency_item_id + ']"]');
        return field ? String(field.value || "").trim().toUpperCase() : "";
    }

    function endDate() {
        if (!context || !context.end_date_item_id) return "";
        var field = document.querySelector('[name="field_value[' + context.end_date_item_id + ']"]');
        return field ? String(field.value || "").trim() : "";
    }

    function isChf(code) {
        return String(code || "").trim().toUpperCase() === "CHF";
    }

    function parseAmount(raw) {
        var text = String(raw == null ? "" : raw).trim().replace(/,/g, "");
        if (!text) return null;
        var number = Number(text);
        return Number.isFinite(number) ? number : null;
    }

    function formatAmount(number) {
        if (number == null || !Number.isFinite(Number(number))) return "";
        return Number(number).toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    function convert(local, rate) {
        var amount = parseAmount(local);
        var divisor = parseAmount(rate);
        if (amount == null || divisor == null || divisor === 0) return null;
        return Math.round(amount * divisor);
    }

    function rateFor(code) {
        if (!context || !context.rates || isChf(code)) return null;
        if (endDate() !== String(context.rate_date || "")) return null;
        var rate = context.rates[String(code || "").trim().toUpperCase()];
        return rate == null ? null : rate;
    }

    function ensureRate(code) {
        var normalized = String(code || "").trim().toUpperCase();
        var day = endDate();
        if (!context || !normalized || isChf(normalized) || !day || rateFor(normalized) != null) {
            paint();
            return;
        }
        var pendingKey = normalized + "|" + day;
        var pending = context._pending || (context._pending = {});
        if (pending[pendingKey]) return;
        pending[pendingKey] = true;
        fetch(
            "/fdrs/exchange-rate?date=" + encodeURIComponent(day) +
            "&currency=" + encodeURIComponent(normalized),
            { credentials: "same-origin", headers: { Accept: "application/json" } }
        )
            .then(function (response) { return response.ok ? response.json() : null; })
            .then(function (data) {
                pending[pendingKey] = false;
                if (!context.rates) context.rates = {};
                if (data && data.rate != null && data.date === day) {
                    context.rate_date = data.date;
                    context.rates = {};
                    context.rates[normalized] = data.rate;
                }
                paint();
            })
            .catch(function () {
                pending[pendingKey] = false;
                paint();
            });
    }

    function formElement() {
        return document.querySelector("form");
    }

    function companionInput(chfItemId) {
        var form = formElement();
        if (!form) return null;
        var name = "indicator_" + chfItemId + "_total_value";
        var input = form.querySelector('input[data-fdrs-chf-companion="' + chfItemId + '"]');
        if (!input) {
            input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.setAttribute("data-fdrs-chf-companion", String(chfItemId));
            form.appendChild(input);
        }
        return input;
    }

    function setCompanion(chfItemId, value) {
        var input = companionInput(chfItemId);
        if (!input) return;
        if (value == null || value === "") {
            input.remove();
            return;
        }
        input.value = String(value);
    }

    function readoutFor(localInput) {
        var block = localInput.closest(".form-item-block") || localInput.parentElement || localInput;
        block.querySelectorAll(".fdrs-chf-readout, .fdrs-chf-cell").forEach(function (old) {
            old.remove();
        });
        var note = block.querySelector(":scope > .fdrs-chf-stripe");
        if (!note) {
            note = document.createElement("div");
            note.className = "fdrs-chf-stripe";
            block.appendChild(note);
        }
        return note;
    }

    function stripeHtml(amount) {
        return "<span>CHF</span><strong>" + formatAmount(amount) + "</strong>";
    }

    function paintPair(pair) {
        var localInput = document.querySelector(
            'input[name="indicator_' + pair.local_item_id + '_total_value"]'
        );
        if (!localInput) return;
        var note = readoutFor(localInput);
        var code = currencyCode();
        var show = code && !isChf(code);
        note.hidden = !show;
        if (!show) {
            if (isChf(code)) setCompanion(pair.chf_item_id, localInput.value);
            else setCompanion(pair.chf_item_id, null);
            return;
        }
        var current = parseAmount(localInput.value);
        var initial = parseAmount(localInput.getAttribute("data-fdrs-initial-local"));
        var rate = rateFor(code);
        var calculated = rate == null ? null : convert(current, rate);
        if (calculated != null) {
            note.innerHTML = stripeHtml(calculated);
            setCompanion(pair.chf_item_id, calculated);
            return;
        }
        var stored = parseAmount(pair.chf_value);
        var unchanged = current === initial;
        if (unchanged && stored != null) {
            note.innerHTML = stripeHtml(stored);
            setCompanion(pair.chf_item_id, null);
            return;
        }
        note.textContent = "Exchange rate for this date is not loaded.";
        setCompanion(pair.chf_item_id, null);
    }

    function fundingCell(row) {
        var marked = row.querySelector("[data-column='Funding']");
        if (marked) return marked.closest("td, th") || marked;
        var cells = row.querySelectorAll(":scope > th, :scope > td");
        for (var i = 0; i < cells.length; i++) {
            if ((cells[i].textContent || "").replace(/\s+/g, " ").trim() === "Funding") return cells[i];
        }
        return null;
    }

    function ensureChfCell(row, after) {
        var existing = row.querySelector(":scope > [data-fdrs-chf-col]");
        if (existing) return existing;
        var cell = document.createElement(after.tagName.toLowerCase() === "th" ? "th" : "td");
        cell.setAttribute("data-fdrs-chf-col", "1");
        cell.className = "fdrs-chf-col border border-gray-300 px-2 py-1";
        if (cell.tagName === "TH") cell.setAttribute("data-fdrs-chf-header", "1");
        after.insertAdjacentElement("afterend", cell);
        return cell;
    }

    function matrixAmount(input, rate, storedMap) {
        var current = parseAmount(input.value);
        var initial = parseAmount(input.getAttribute("data-fdrs-initial-local"));
        var calculated = rate == null ? null : convert(current, rate);
        if (calculated != null) return calculated;
        var key = input.getAttribute("data-cell-key") || "";
        var stored = storedMap ? parseAmount(storedMap[key]) : null;
        if (current === initial && stored != null) return stored;
        return null;
    }

    function paintMatrix() {
        var matrix = context && context.matrix;
        if (!matrix) return;
        var container = document.querySelector('.matrix-container[data-field-id="' + matrix.item_id + '"]');
        if (!container) return;
        container.querySelectorAll(".fdrs-chf-cell").forEach(function (old) { old.remove(); });
        var code = currencyCode();
        var show = code && !isChf(code);
        if (!show) {
            container.querySelectorAll("[data-fdrs-chf-col]").forEach(function (cell) { cell.remove(); });
            return;
        }
        var rate = rateFor(code);
        var storedMap = matrix.chf || {};
        var total = 0;
        var any = false;
        container.querySelectorAll("tr.matrix-data-row input[data-column='" + (matrix.column || "Funding") + "']").forEach(function (input) {
            var amount = matrixAmount(input, rate, storedMap);
            if (amount != null) {
                total += amount;
                any = true;
            }
        });
        container.querySelectorAll("tr").forEach(function (row) {
            var anchor = fundingCell(row);
            if (!anchor) return;
            var cell = ensureChfCell(row, anchor);
            if (cell.tagName === "TH") {
                cell.textContent = "CHF";
                return;
            }
            var input = row.querySelector("input[data-column='" + (matrix.column || "Funding") + "']");
            if (input) {
                var amount = matrixAmount(input, rate, storedMap);
                cell.textContent = amount == null ? "—" : formatAmount(amount);
                cell.classList.remove("is-total");
                return;
            }
            if (row.classList.contains("matrix-column-totals-row")) {
                cell.textContent = any ? formatAmount(total) : "—";
                cell.classList.add("is-total");
                return;
            }
            cell.textContent = "—";
        });
    }

    function paint() {
        if (!context) return;
        (context.pairs || []).forEach(paintPair);
        paintMatrix();
    }

    function rememberInitial() {
        (context.pairs || []).forEach(function (pair) {
            var localInput = document.querySelector(
                'input[name="indicator_' + pair.local_item_id + '_total_value"]'
            );
            if (localInput && !localInput.hasAttribute("data-fdrs-initial-local")) {
                localInput.setAttribute("data-fdrs-initial-local", localInput.value || "");
            }
        });
        if (!context.matrix) return;
        var container = document.querySelector(
            '.matrix-container[data-field-id="' + context.matrix.item_id + '"]'
        );
        if (!container) return;
        container.querySelectorAll('input[data-column="' + (context.matrix.column || "Funding") + '"]').forEach(function (input) {
            if (!input.hasAttribute("data-fdrs-initial-local")) {
                input.setAttribute("data-fdrs-initial-local", input.value || "");
            }
        });
    }

    function bind() {
        document.addEventListener("input", function (event) {
            var target = event.target;
            if (!target || !target.closest) return;
            if (target.name && String(target.name).indexOf("indicator_") === 0) {
                paint();
            }
            if (target.name && String(target.name).indexOf("field_value[") === 0) {
                ensureRate(currencyCode());
            }
            if (target.getAttribute && target.getAttribute("data-column")) paint();
        });
        document.addEventListener("change", function (event) {
            var target = event.target;
            if (!target || !target.name) return;
            if (String(target.name).indexOf("field_value[") === 0) ensureRate(currencyCode());
        });
        if (window.jQuery) {
            window.jQuery(document).on("change select2:select", "[name^='field_value']", function () {
                ensureRate(currencyCode());
            });
        }
    }

    function start() {
        var id = aesId();
        if (!id) return;
        fetch("/fdrs/entry-currency?aes_id=" + encodeURIComponent(id), {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        })
            .then(function (response) {
                if (!response.ok) return null;
                return response.json();
            })
            .then(function (payload) {
                if (!payload || (!payload.pairs && !payload.matrix)) return;
                context = payload;
                rememberInitial();
                bind();
                ensureRate(currencyCode());
                window.setTimeout(paint, 600);
                window.setTimeout(paint, 2000);
            })
            .catch(function () {});
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
