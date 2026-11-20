/*
 * Draws the plan's activities inside each DREF sector.
 * A focal point reports progress on those activities and cannot add one.
 * Sectors that are not on this operation's plan, or that have no visible
 * fields and no activities, are removed from the section navigation.
 */
(function () {
    "use strict";

    function labelText(labels, key, fallback) {
        return labels && labels[key] ? labels[key] : fallback;
    }

    function field(caption, control, width) {
        var wrap = document.createElement("label");
        wrap.className = "dref-plan-field dref-plan-field--" + width;
        var span = document.createElement("span");
        span.textContent = caption;
        wrap.appendChild(span);
        wrap.appendChild(control);
        return wrap;
    }

    function readOnlyInput(value) {
        var input = document.createElement("input");
        input.value = value || "";
        input.readOnly = true;
        input.tabIndex = -1;
        return input;
    }

    function numberInput(name, value, editable) {
        var input = document.createElement("input");
        input.type = "number";
        input.min = "0";
        input.name = name;
        input.value = value || "";
        if (!editable) input.disabled = true;
        return input;
    }

    function card(row, labels, statuses, editable) {
        var article = document.createElement("article");
        article.className = "dref-plan-activity";

        article.appendChild(field(labelText(labels, "activity", "Activity"), readOnlyInput(row.title), 12));

        var status = document.createElement("select");
        status.name = "activity_" + row.id + "_status";
        (statuses || []).forEach(function (option) {
            var item = document.createElement("option");
            item.value = option.value;
            item.textContent = option.label;
            if (option.value === row.status) item.selected = true;
            status.appendChild(item);
        });
        if (!editable) status.disabled = true;
        article.appendChild(field(labelText(labels, "status", "Status"), status, 4));
        article.appendChild(field(labelText(labels, "activity_type", "Activity type"), readOnlyInput(row.activity_type), 4));
        article.appendChild(field(labelText(labels, "carried_out_by", "Activity carried out by"), readOnlyInput(row.carried_out_by), 4));
        article.appendChild(field(labelText(labels, "activity_budget", "Budget"), readOnlyInput(row.budget), 3));
        article.appendChild(field(labelText(labels, "activity_target", "Target"), readOnlyInput(row.target), 3));
        article.appendChild(field(labelText(labels, "start_date", "Start date"), readOnlyInput(row.start_date), 3));
        article.appendChild(field(labelText(labels, "end_date", "End date"), readOnlyInput(row.end_date), 3));
        article.appendChild(field(
            labelText(labels, "reached", "Reached - total"),
            numberInput("activity_" + row.id + "_reached", row.reached, editable),
            4
        ));
        [
            ["pct_female", "pct_women", "% Female"],
            ["pct_male", "pct_men", "% Male"],
            ["pct_girls", "pct_girls", "% Girls"],
            ["pct_boys", "pct_boys", "% Boys"]
        ].forEach(function (part) {
            article.appendChild(field(
                labelText(labels, part[0], part[2]),
                numberInput("activity_" + row.id + "_" + part[1], row[part[1]], editable),
                2
            ));
        });

        var box = document.createElement("input");
        box.type = "checkbox";
        box.name = "activity_" + row.id + "_disaggregation_na";
        box.value = "1";
        box.checked = !!row.disaggregation_na;
        if (!editable) box.disabled = true;
        var na = field(labelText(labels, "disaggregation_na", "Can't provide disaggregation"), box, 12);
        na.classList.add("dref-plan-field--check");
        article.appendChild(na);
        return article;
    }

    function setListed(section, listed) {
        var link = document.querySelector(
            '#section-navigation-sidebar a.section-link[data-section-id="' + section.id + '"]'
        );
        if (!link) return;
        var item = link.closest("li");
        if (!item) return;
        item.hidden = !listed;
        item.classList.toggle("hidden", !listed);
        item.style.display = listed ? "" : "none";
    }

    function hasVisibleItems(section) {
        var blocks = section.querySelectorAll("[data-item-type]");
        for (var i = 0; i < blocks.length; i++) {
            if (!blocks[i].hidden && !blocks[i].classList.contains("relevance-hidden")) return true;
        }
        return false;
    }

    function conceal(section) {
        section.hidden = true;
        setListed(section, false);
    }

    function reveal(section) {
        section.hidden = false;
        setListed(section, true);
    }

    function applyPlan(payload) {
        var allowed = {};
        (payload.indicator_bank_ids || []).forEach(function (id) {
            allowed[String(id)] = true;
        });
        var sectors = {};
        (payload.sector_keys || []).forEach(function (key) {
            sectors[key] = true;
        });
        var activitySections = payload.sections || {};
        document.querySelectorAll('[data-entry-render="dref-sector"]').forEach(function (section) {
            var key = section.getAttribute("data-entry-key");
            if (!sectors[key]) {
                conceal(section);
                return;
            }
            if (payload.filter_indicators) {
                section.querySelectorAll('[data-item-type="indicator"]').forEach(function (block) {
                    var id = block.getAttribute("data-indicator-bank-id");
                    block.hidden = !id || !allowed[id];
                });
            }
            var rows = activitySections[key] || [];
            if (!hasVisibleItems(section) && !rows.length) {
                conceal(section);
                return;
            }
            reveal(section);
        });
    }

    function render(payload) {
        applyPlan(payload);
        var sections = payload.sections || {};
        var labels = payload.labels || {};
        document.querySelectorAll('[data-entry-render="dref-sector"]').forEach(function (section) {
            if (section.hidden || section.dataset.drefActivitiesReady) return;
            section.dataset.drefActivitiesReady = "1";
            var rows = sections[section.getAttribute("data-entry-key")] || [];
            if (!rows.length) return;
            var sample = section.querySelector("input, select, textarea");
            var editable = !sample || !sample.disabled;
            var host = document.createElement("div");
            host.className = "dref-plan-activities";
            var heading = document.createElement("h4");
            heading.className = "dref-plan-activities__title";
            heading.textContent = "Selected activities";
            host.appendChild(heading);
            rows.forEach(function (row) {
                host.appendChild(card(row, labels, payload.statuses, editable));
            });
            var content = section.querySelector("[data-collapsible-content]") || section;
            content.appendChild(host);
        });
    }

    function start() {
        var sector = document.querySelector('[data-entry-render="dref-sector"]');
        if (!sector) return;
        var match = window.location.pathname.match(/\/assignment\/(\d+)/);
        var aesId = match && match[1];
        if (!aesId) return;
        fetch("/dref-monitoring/assignment/" + aesId + "/activities", { credentials: "same-origin" })
            .then(function (response) { return response.ok ? response.json() : null; })
            .then(function (payload) { if (payload) render(payload); })
            .catch(function () { /* the sector still shows its indicators */ });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
