/*
 * Draws the plan's activities inside each DREF sector, under the indicator
 * they belong to. A focal point reports progress on those activities and cannot add one.
 * Sectors that are not on this operation's plan, or that have no visible
 * fields and no activities, are removed from the section navigation.
 * Plan indicators the template has no field for are listed in their sector
 * with a flag. That listing is temporary.
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

    function staticText(value) {
        var text = document.createElement("div");
        text.className = "dref-plan-static";
        text.textContent = value || "";
        return text;
    }

    function choiceSelect(name, options, selected, editable, blankLabel) {
        var select = document.createElement("select");
        select.name = name;
        var blank = document.createElement("option");
        blank.value = "";
        blank.textContent = blankLabel || "Select";
        if (!selected) blank.selected = true;
        select.appendChild(blank);
        (options || []).forEach(function (option) {
            var item = document.createElement("option");
            item.value = option.value;
            item.textContent = option.label;
            if (option.value === selected) item.selected = true;
            select.appendChild(item);
        });
        if (!editable) select.disabled = true;
        return select;
    }

    function numberInput(name, value, editable, options) {
        var input = document.createElement("input");
        input.type = "number";
        input.min = "0";
        input.name = name;
        input.value = value || "";
        if (options && options.max != null) input.max = String(options.max);
        if (options && options.step) input.step = options.step;
        if (!editable) input.disabled = true;
        return input;
    }

    function dateInput(name, value, editable) {
        var input = document.createElement("input");
        input.type = "date";
        input.name = name;
        input.value = value || "";
        if (!editable) input.disabled = true;
        return input;
    }

    var uiLabels = {};
    // Section-level "Collapse all indicators / activities" is off for now.
    var collapseAllEnabled = false;

    function collapseWord(collapsed) {
        return labelText(uiLabels, collapsed ? "expand" : "collapse", collapsed ? "Expand" : "Collapse");
    }

    function collapseButton() {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "dref-collapse";
        button.setAttribute("aria-expanded", "true");
        button.setAttribute("aria-label", collapseWord(false));
        return button;
    }

    function collapseButtonFor(node) {
        for (var i = 0; i < node.children.length; i++) {
            if (node.children[i].classList.contains("dref-collapse")) return node.children[i];
        }
        return null;
    }

    function setCollapsed(node, collapsed) {
        node.classList.toggle("is-collapsed", collapsed);
        var button = collapseButtonFor(node);
        if (!button) return;
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
        button.setAttribute("aria-label", collapseWord(collapsed));
    }

    function visibleIndicators() {
        var found = [];
        document.querySelectorAll('[data-entry-render="dref-sector"] [data-item-type="indicator"], [data-entry-render="dref-sector"] .dref-unmatched-indicator').forEach(function (node) {
            if (node.hidden || node.closest("[hidden]")) return;
            found.push(node);
        });
        return found;
    }

    function markIndicatorButtons() {
        visibleIndicators().forEach(function (node) {
            if (node.classList.contains("dref-unmatched-indicator")) return;
            if (collapseButtonFor(node)) return;
            var placed = false;
            for (var i = 0; i < node.children.length; i++) {
                if (node.children[i].classList.contains("dref-plan-activities")) placed = true;
            }
            if (!placed) return;
            node.appendChild(collapseButton());
        });
    }

    function allCollapsed(nodes) {
        if (!nodes.length) return false;
        for (var i = 0; i < nodes.length; i++) {
            if (!nodes[i].classList.contains("is-collapsed")) return false;
        }
        return true;
    }

    function sectionNodes(section, kind) {
        if (!section) return [];
        if (kind === "activities") return section.querySelectorAll(".dref-plan-activity");
        var found = [];
        section.querySelectorAll('[data-item-type="indicator"], .dref-unmatched-indicator').forEach(function (node) {
            if (node.hidden || node.closest("[hidden]")) return;
            found.push(node);
        });
        return found;
    }

    function buttonLabel(kind, collapsed) {
        var collapseKey = kind === "activities" ? "collapse_activities" : "collapse_indicators";
        var expandKey = kind === "activities" ? "expand_activities" : "expand_indicators";
        var collapseText = kind === "activities" ? "Collapse all activities" : "Collapse all indicators";
        var expandText = kind === "activities" ? "Expand all activities" : "Expand all indicators";
        return labelText(uiLabels, collapsed ? expandKey : collapseKey, collapsed ? expandText : collapseText);
    }

    function refreshSectionButtons(section) {
        ["indicators", "activities"].forEach(function (kind) {
            var button = section.querySelector('[data-dref-collapse-all="' + kind + '"]');
            if (!button) return;
            var nodes = sectionNodes(section, kind);
            var collapsed = allCollapsed(nodes);
            button.setAttribute("aria-pressed", collapsed ? "true" : "false");
            button.textContent = buttonLabel(kind, collapsed);
        });
    }

    function sectionHeading(section) {
        var children = section.children;
        for (var i = 0; i < children.length; i++) {
            if (children[i].tagName === "H3") return children[i];
        }
        return null;
    }

    function installSectionControls(section) {
        var heading = sectionHeading(section);
        if (!heading || heading.querySelector(".dref-collapse-all")) return;
        var kinds = [];
        if (sectionNodes(section, "indicators").length) kinds.push("indicators");
        if (sectionNodes(section, "activities").length) kinds.push("activities");
        if (!kinds.length) return;
        var bar = document.createElement("div");
        bar.className = "dref-collapse-all";
        kinds.forEach(function (kind) {
            var button = document.createElement("button");
            button.type = "button";
            button.setAttribute("data-dref-collapse-all", kind);
            bar.appendChild(button);
        });
        var toggle = heading.querySelector(".collapse-toggle");
        if (toggle) heading.insertBefore(bar, toggle);
        else heading.appendChild(bar);
        refreshSectionButtons(section);
    }

    function installCollapseControls() {
        if (!collapseAllEnabled) return;
        document.querySelectorAll('[data-entry-render="dref-sector"]').forEach(function (section) {
            if (section.hidden) return;
            installSectionControls(section);
        });
    }

    function onCollapseClick(event) {
        var all = event.target.closest("[data-dref-collapse-all]");
        if (all) {
            event.preventDefault();
            event.stopPropagation();
            var section = all.closest('[data-entry-render="dref-sector"]');
            var kind = all.getAttribute("data-dref-collapse-all");
            var nodes = sectionNodes(section, kind);
            var collapsed = !allCollapsed(nodes);
            for (var i = 0; i < nodes.length; i++) setCollapsed(nodes[i], collapsed);
            refreshSectionButtons(section);
            return;
        }
        var one = event.target.closest(".dref-collapse");
        if (!one) return;
        event.preventDefault();
        var activity = one.closest(".dref-plan-activity");
        var indicator = activity ? null : one.closest(".dref-unmatched-indicator, [data-item-type='indicator']");
        var node = activity || indicator;
        if (!node) return;
        setCollapsed(node, !node.classList.contains("is-collapsed"));
        var owner = node.closest('[data-entry-render="dref-sector"]');
        if (owner) refreshSectionButtons(owner);
    }

    function card(row, labels, statuses, editable, choices) {
        var article = document.createElement("article");
        article.className = "dref-plan-activity";

        var top = document.createElement("div");
        top.className = "dref-plan-activity__top";
        top.appendChild(field(labelText(labels, "activity", "Activity"), staticText(row.title), 12));
        article.appendChild(top);
        article.appendChild(collapseButton());

        var body = document.createElement("div");
        body.className = "dref-plan-activity__body";
        article.appendChild(body);

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
        choices = choices || {};
        body.appendChild(field(labelText(labels, "status", "Status"), status, 4));
        body.appendChild(field(
            labelText(labels, "activity_type", "Activity type"),
            choiceSelect(
                "activity_" + row.id + "_activity_type",
                choices.activity_type,
                row.activity_type,
                editable,
                choices.blank
            ),
            4
        ));
        body.appendChild(field(
            labelText(labels, "carried_out_by", "Activity carried out by"),
            choiceSelect(
                "activity_" + row.id + "_carried_out_by",
                choices.carried_out_by,
                row.carried_out_by,
                editable,
                choices.blank
            ),
            4
        ));
        body.appendChild(field(
            labelText(labels, "activity_budget", "Budget"),
            numberInput("activity_" + row.id + "_budget", row.budget, editable, { step: "0.01" }),
            3
        ));
        body.appendChild(field(
            labelText(labels, "activity_target", "Target"),
            numberInput("activity_" + row.id + "_target", row.target, editable, { step: "any" }),
            3
        ));
        body.appendChild(field(
            labelText(labels, "start_date", "Start date"),
            dateInput("activity_" + row.id + "_start_date", row.start_date, editable),
            3
        ));
        body.appendChild(field(
            labelText(labels, "end_date", "End date"),
            dateInput("activity_" + row.id + "_end_date", row.end_date, editable),
            3
        ));
        body.appendChild(field(
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
            var slot = field(
                labelText(labels, part[0], part[2]),
                numberInput("activity_" + row.id + "_" + part[1], row[part[1]], editable, { max: 100, step: "1" }),
                2
            );
            slot.classList.add("dref-plan-field--disagg");
            body.appendChild(slot);
        });

        var box = document.createElement("input");
        box.type = "checkbox";
        box.name = "activity_" + row.id + "_disaggregation_na";
        box.value = "1";
        box.checked = !!row.disaggregation_na;
        if (!editable) box.disabled = true;
        var na = field(labelText(labels, "disaggregation_na", "Can't provide disaggregation"), box, 12);
        na.classList.add("dref-plan-field--check");
        body.appendChild(na);

        var reason = document.createElement("textarea");
        reason.name = "activity_" + row.id + "_disaggregation_reason";
        reason.rows = 2;
        reason.value = row.disaggregation_reason || "";
        if (!editable) reason.disabled = true;
        var reasonField = field(
            labelText(uiLabels, "disaggregation_reason", "Why is this data not available?"),
            reason,
            12
        );
        reasonField.classList.add("dref-plan-field--reason");
        body.appendChild(reasonField);
        if (!editable) article.setAttribute("data-dref-locked", "1");
        box.addEventListener("change", function () {
            setDisaggregationUnavailable(article, box.checked);
        });
        setDisaggregationUnavailable(article, box.checked);
        return article;
    }

    function setDisaggregationUnavailable(article, unavailable) {
        var locked = article.hasAttribute("data-dref-locked");
        article.querySelectorAll(".dref-plan-field--disagg").forEach(function (slot) {
            slot.classList.toggle("is-unavailable", unavailable);
            var input = slot.querySelector("input");
            if (!input) return;
            if (unavailable) input.value = "";
            input.disabled = unavailable || locked;
        });
        var reasonField = article.querySelector(".dref-plan-field--reason");
        if (!reasonField) return;
        reasonField.hidden = !unavailable;
        var area = reasonField.querySelector("textarea");
        if (!area) return;
        area.required = unavailable && !locked;
        if (!unavailable) {
            area.value = "";
            area.setCustomValidity("");
        }
    }

    function revealActivity(article) {
        var section = article.closest('[data-entry-render="dref-sector"]');
        if (section) {
            var toggle = section.querySelector(":scope > h3 .collapse-toggle");
            if (toggle && toggle.getAttribute("aria-expanded") === "false") toggle.click();
        }
        var indicator = article.closest(".dref-unmatched-indicator, [data-item-type='indicator']");
        if (indicator && indicator.classList.contains("is-collapsed")) setCollapsed(indicator, false);
        if (article.classList.contains("is-collapsed")) setCollapsed(article, false);
        if (section) refreshSectionButtons(section);
    }

    function missingDisaggregationReason() {
        var missing = null;
        document.querySelectorAll(".dref-plan-activity").forEach(function (article) {
            var box = article.querySelector('input[name$="_disaggregation_na"]');
            var area = article.querySelector(".dref-plan-field--reason textarea");
            if (!box || !box.checked || !area || area.value.trim()) return;
            if (!missing) missing = { article: article, area: area };
        });
        if (missing) return missing;
        document.querySelectorAll(".dref-report-field [data-activity-id]").forEach(function (block) {
            var box = block.querySelector('[data-part="disaggregation_na"]');
            var area = block.querySelector('[data-part="disaggregation_reason"]');
            if (!box || !box.checked || !area || area.value.trim()) return;
            if (!missing) missing = { article: block, area: area };
        });
        return missing;
    }

    function demandDisaggregationReason(missing) {
        if (missing.article.classList) revealActivity(missing.article);
        var reasonField = missing.area.closest(".dref-plan-field--reason, .dref-disagg-reason");
        if (reasonField) reasonField.hidden = false;
        window.setTimeout(function () {
            missing.area.setCustomValidity(labelText(
                uiLabels,
                "disaggregation_reason_required",
                "Explain why this data is not available."
            ));
            missing.area.reportValidity();
            missing.area.focus();
        }, 250);
    }

    var SHARE_PARTS = ["pct_women", "pct_men", "pct_girls", "pct_boys"];

    function percentNumber(input) {
        var text = String(input.value || "").replace(/,/g, "").trim();
        if (!text) return null;
        var parsed = Number(text);
        return Number.isFinite(parsed) ? parsed : null;
    }

    function percentageProblem() {
        var found = null;
        document.querySelectorAll(".dref-plan-activity").forEach(function (article) {
            if (found) return;
            var inputs = SHARE_PARTS.map(function (part) {
                return article.querySelector('input[name$="_' + part + '"]');
            }).filter(function (input) {
                return input && !input.disabled;
            });
            var over = null;
            var sum = 0;
            var any = false;
            inputs.forEach(function (input) {
                var value = percentNumber(input);
                if (value === null) return;
                any = true;
                sum += value;
                if (value > 100 && !over) over = input;
            });
            if (over) {
                found = {
                    article: article,
                    field: over,
                    message: labelText(uiLabels, "percent_each", "A percentage cannot be more than 100.")
                };
                return;
            }
            if (any && sum > 100 + 1e-9) {
                found = {
                    article: article,
                    field: inputs[0],
                    message: labelText(uiLabels, "percent_sum", "The percentages together cannot be more than 100.")
                };
            }
        });
        return found;
    }

    function demandField(problem) {
        if (problem.article.classList) revealActivity(problem.article);
        window.setTimeout(function () {
            problem.field.setCustomValidity(problem.message);
            problem.field.reportValidity();
            problem.field.focus();
        }, 250);
    }

    function saveProblem() {
        return percentageProblem() || missingDisaggregationReason();
    }

    function installDisaggregationGuard() {
        var form = document.getElementById("focalDataEntryForm") || document.querySelector("form");
        if (!form || form.getAttribute("data-dref-disagg-guard")) return;
        form.setAttribute("data-dref-disagg-guard", "1");
        // Save is sent from the button click and never fires submit, so both paths are checked.
        function stop(event) {
            var problem = saveProblem();
            if (!problem) return;
            event.preventDefault();
            event.stopPropagation();
            if (problem.area) demandDisaggregationReason(problem);
            else demandField(problem);
        }
        form.addEventListener("click", function (event) {
            var button = event.target.closest("button[type='submit']");
            if (!button || !form.contains(button)) return;
            stop(event);
        }, true);
        form.addEventListener("submit", stop, true);
        form.addEventListener("input", function (event) {
            var area = event.target;
            if (!area.matches) return;
            if (area.matches(".dref-plan-field--reason textarea, [data-part='disaggregation_reason']")) {
                if (area.value.trim()) area.setCustomValidity("");
                return;
            }
            if (area.matches(".dref-plan-field--disagg input")) area.setCustomValidity("");
        });
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

    function extraSectionKeys(payload) {
        var keys = {};
        (payload.extra_indicators || []).forEach(function (row) {
            if (row.section_key) keys[row.section_key] = true;
        });
        return keys;
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
        var extras = extraSectionKeys(payload);
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
            if (!hasVisibleItems(section) && !rows.length && !extras[key]) {
                conceal(section);
                return;
            }
            reveal(section);
        });
    }

    function findSection(key) {
        var nodes = document.querySelectorAll('[data-entry-render="dref-sector"]');
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].getAttribute("data-entry-key") === key) return nodes[i];
        }
        return null;
    }

    function alreadyListed(row) {
        if (!row.bank_id) return false;
        var wanted = String(row.bank_id);
        var blocks = document.querySelectorAll('[data-item-type="indicator"]');
        for (var i = 0; i < blocks.length; i++) {
            var block = blocks[i];
            if (block.hidden || block.closest("[hidden]")) continue;
            if (block.getAttribute("data-indicator-bank-id") === wanted) return true;
        }
        return false;
    }

    function flagIcon(text) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "dref-unmatched-flag";
        button.setAttribute("aria-label", text);
        var tip = document.createElement("span");
        tip.className = "dref-unmatched-flag__tip";
        tip.setAttribute("role", "tooltip");
        tip.textContent = text;
        button.appendChild(tip);
        return button;
    }

    function extraCard(row, labels) {
        var article = document.createElement("article");
        article.className = "dref-unmatched-indicator";
        article.setAttribute("data-dref-extra-indicator", String(row.id));

        var rowEl = document.createElement("div");
        rowEl.className = "dref-unmatched-indicator__row";

        var name = document.createElement("div");
        name.className = "dref-unmatched-indicator__name";

        var caption = document.createElement("p");
        caption.className = "dref-unmatched-indicator__caption";
        caption.textContent = labelText(labels, "indicator", "Indicator");
        name.appendChild(caption);

        var titleLine = document.createElement("div");
        titleLine.className = "dref-unmatched-indicator__title-line";
        var title = document.createElement("div");
        title.className = "dref-unmatched-indicator__title";
        title.textContent = row.title || "";
        titleLine.appendChild(title);
        if (row.flag) titleLine.appendChild(flagIcon(row.flag));
        name.appendChild(titleLine);

        var more = document.createElement("div");
        more.className = "dref-unmatched-indicator__more";
        if (row.unit) {
            var unit = document.createElement("p");
            unit.className = "dref-unmatched-indicator__unit";
            unit.textContent = row.unit;
            more.appendChild(unit);
        }
        if (row.bank_name) {
            var bank = document.createElement("p");
            bank.className = "dref-unmatched-indicator__bank";
            bank.textContent = row.bank_name;
            more.appendChild(bank);
        }

        var target = document.createElement("label");
        target.className = "dref-unmatched-indicator__target";
        var span = document.createElement("span");
        span.textContent = labelText(labels, "target", "Target");
        target.appendChild(span);
        target.appendChild(readOnlyInput(row.target));

        rowEl.appendChild(name);
        rowEl.appendChild(target);
        article.appendChild(rowEl);
        article.appendChild(more);
        article.appendChild(collapseButton());
        return article;
    }

    function orphanSection(key, label) {
        var section = document.createElement("div");
        section.className = "dref-unmatched-section";
        section.setAttribute("data-entry-render", "dref-sector");
        section.setAttribute("data-entry-key", key);
        var heading = document.createElement("h3");
        heading.textContent = label || key;
        section.appendChild(heading);
        var report = document.querySelector('[data-entry-render="dref-report"]');
        var sectors = document.querySelectorAll('[data-entry-render="dref-sector"]');
        var anchor = report || (sectors.length ? sectors[sectors.length - 1] : null);
        if (anchor && anchor.parentNode) {
            anchor.parentNode.insertBefore(section, report ? report : anchor.nextSibling);
        } else {
            var form = document.querySelector("form");
            if (form) form.appendChild(section);
        }
        return section;
    }

    function placeExtraIndicators(payload) {
        var groups = {};
        var order = [];
        (payload.extra_indicators || []).forEach(function (row) {
            var key = row.section_key || "";
            if (!groups[key]) {
                groups[key] = [];
                order.push(key);
            }
            groups[key].push(row);
        });
        order.forEach(function (key) {
            var section = findSection(key);
            var rows = groups[key].filter(function (row) {
                return !alreadyListed(row);
            });
            if (!rows.length) return;
            if (!section) section = orphanSection(key, rows[0].section_label);
            if (section.dataset.drefExtrasReady) return;
            section.dataset.drefExtrasReady = "1";
            reveal(section);
            var host = document.createElement("div");
            host.className = "dref-unmatched-indicators";
            rows.forEach(function (row) {
                host.appendChild(extraCard(row, payload.extra_labels));
            });
            var content = section.querySelector("[data-collapsible-content]") || section;
            var activities = content.querySelector(".dref-plan-activities");
            if (activities) content.insertBefore(host, activities);
            else content.appendChild(host);
        });
    }

    function firstEditableControl(root) {
        var controls = root.querySelectorAll("input, select, textarea");
        for (var i = 0; i < controls.length; i++) {
            if (controls[i].closest(".dref-unmatched-indicator")) continue;
            return controls[i];
        }
        return null;
    }

    function sectionIsEditable(section) {
        var sample = firstEditableControl(section);
        if (!sample) {
            var form = section.closest("form");
            sample = form ? firstEditableControl(form) : null;
        }
        return !sample || !sample.disabled;
    }

    function anchorFor(section, row) {
        var blocks = section.querySelectorAll('[data-item-type="indicator"]');
        if (row.indicator_bank_id) {
            var wanted = String(row.indicator_bank_id);
            for (var i = 0; i < blocks.length; i++) {
                var block = blocks[i];
                if (block.hidden || block.closest("[hidden]")) continue;
                if (block.getAttribute("data-indicator-bank-id") === wanted) return block;
            }
        }
        if (row.indicator_id) {
            var extras = section.querySelectorAll("[data-dref-extra-indicator]");
            var planId = String(row.indicator_id);
            for (var j = 0; j < extras.length; j++) {
                if (extras[j].getAttribute("data-dref-extra-indicator") === planId) return extras[j];
            }
        }
        return null;
    }

    function anchorKey(anchor) {
        var bank = anchor.getAttribute("data-indicator-bank-id");
        if (bank) return "bank:" + bank;
        return "plan:" + (anchor.getAttribute("data-dref-extra-indicator") || "");
    }

    function hostAfter(anchor, key) {
        var children = anchor.children;
        for (var i = 0; i < children.length; i++) {
            if (children[i].getAttribute("data-dref-under") === key) return children[i];
        }
        var host = document.createElement("div");
        host.className = "dref-plan-activities dref-plan-activities--under";
        host.setAttribute("data-dref-under", key);
        anchor.appendChild(host);
        return host;
    }

    function placeActivities(payload) {
        var sections = payload.sections || {};
        var labels = payload.labels || {};
        var extraLabels = payload.extra_labels || {};
        document.querySelectorAll('[data-entry-render="dref-sector"]').forEach(function (section) {
            if (section.hidden || section.dataset.drefActivitiesReady) return;
            section.dataset.drefActivitiesReady = "1";
            var rows = sections[section.getAttribute("data-entry-key")] || [];
            if (!rows.length) return;
            var editable = sectionIsEditable(section);
            var posted = payload.choices || {};
            var choices = {
                activity_type: posted.activity_type || [],
                carried_out_by: posted.carried_out_by || [],
                blank: labelText(extraLabels, "select", "Select"),
            };
            var loose = [];
            rows.forEach(function (row) {
                var anchor = anchorFor(section, row);
                if (!anchor) {
                    loose.push(row);
                    return;
                }
                var key = anchorKey(anchor);
                hostAfter(anchor, key).appendChild(card(row, labels, payload.statuses, editable, choices));
            });
            if (!loose.length) return;
            var host = document.createElement("div");
            host.className = "dref-plan-activities";
            host.setAttribute("data-dref-under", "other");
            var heading = document.createElement("h4");
            heading.className = "dref-plan-activities__title";
            heading.textContent = labelText(extraLabels, "other_activities", "Other activities");
            host.appendChild(heading);
            loose.forEach(function (row) {
                host.appendChild(card(row, labels, payload.statuses, editable, choices));
            });
            var content = section.querySelector("[data-collapsible-content]") || section;
            content.appendChild(host);
        });
    }

    function render(payload) {
        uiLabels = payload.extra_labels || {};
        applyPlan(payload);
        placeExtraIndicators(payload);
        placeActivities(payload);
        markIndicatorButtons();
        installCollapseControls();
        installDisaggregationGuard();
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

    document.addEventListener("click", onCollapseClick);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();
