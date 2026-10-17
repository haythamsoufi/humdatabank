(function () {
    "use strict";

    var ICONS = {
        umbrella: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><path d="M24 40 V22"/><path d="M8 22c0-9 7-16 16-16s16 7 16 16"/><path d="M8 22h32"/><path d="M16 22c0 4 8 4 8 0"/><path d="M24 22c0 4 8 4 8 0"/><path d="M24 40c4 0 6-2 6-4"/></svg>',
        virus: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><circle cx="24" cy="24" r="8"/><path d="M24 6v6M24 36v6M6 24h6M36 24h6M11 11l4 4M33 33l4 4M37 11l-4 4M15 33l-4 4"/></svg>',
        people: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><circle cx="16" cy="14" r="4"/><circle cx="32" cy="16" r="3.2"/><path d="M8 34c1-6 5-9 8-9s7 3 8 9"/><path d="M26 34c.6-4 3-7 6-7s5 2 6 7"/></svg>',
        card: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><rect x="8" y="14" width="32" height="20" rx="2"/><path d="M8 20h32M14 28h8"/></svg>',
        megaphone: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><path d="M10 20h8l16-8v24L18 28h-8z"/><path d="M18 28v6c0 3-4 4-6 2"/></svg>',
        tap: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><path d="M18 10v10a8 8 0 0 0 16 0V14"/><path d="M30 14h6"/><path d="M24 28v8"/><path d="M16 40h16"/></svg>',
        group: '<svg viewBox="0 0 48 48" fill="none" stroke="#243044" stroke-width="1.7"><circle cx="24" cy="14" r="4"/><circle cx="12" cy="18" r="3"/><circle cx="36" cy="18" r="3"/><path d="M16 36c1-6 4-9 8-9s7 3 8 9"/><path d="M6 36c.5-4 2-6 5-6"/><path d="M42 36c-.5-4-2-6-5-6"/></svg>',
        pin: '<svg viewBox="0 0 48 48" fill="none" stroke="#e30613" stroke-width="1.7"><path d="M24 42s12-12 12-20a12 12 0 1 0-24 0c0 8 12 20 12 20z"/><circle cx="24" cy="22" r="4"/></svg>'
    };

    var root = document.getElementById("ppp-app");
    var body = document.body;
    var view = body.getAttribute("data-view") || "overview";
    var dataUrl = body.getAttribute("data-url");
    var map = null;

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function icon(name) {
        var wrap = el("span", "ppp-icon");
        wrap.innerHTML = ICONS[name] || "";
        return wrap;
    }

    function compact(value) {
        var number = Number(value) || 0;
        if (number >= 1000000) return (number / 1000000).toFixed(1) + "M";
        if (number >= 1000) return (number / 1000).toFixed(1) + "K";
        return String(Math.round(number));
    }

    function full(value) {
        return Math.round(Number(value) || 0).toLocaleString("en-US");
    }

    function selected(select) {
        return select ? select.value : "";
    }

    function filteredCountries(dashboard, filters) {
        return (dashboard.countries || []).filter(function (country) {
            if (filters.region && country.region !== filters.region) return false;
            if (filters.country && String(country.id) !== String(filters.country)) return false;
            return true;
        });
    }

    function sumKey(countries, bag, key) {
        return countries.reduce(function (total, country) {
            return total + (Number((country[bag] || {})[key]) || 0);
        }, 0);
    }

    function sumReached(countries) {
        return countries.reduce(function (total, country) {
            return total + (Number(country.reached) || 0);
        }, 0);
    }

    function option(value, label) {
        var node = el("option", "", label);
        node.value = value;
        return node;
    }

    function selectControl(labelText, name, choices, current) {
        var label = el("label");
        label.appendChild(document.createTextNode(labelText));
        var select = el("select");
        select.name = name;
        choices.forEach(function (choice) {
            var node = option(choice.value, choice.label);
            if (String(choice.value) === String(current || "")) node.selected = true;
            select.appendChild(node);
        });
        label.appendChild(select);
        return label;
    }

    function renderOverview(dashboard, stage) {
        var filters = { region: "", viewBy: "country" };
        stage.classList.remove("ppp-stage--detail");
        stage.replaceChildren();

        var tools = el("div", "ppp-map-tools");
        var regionChoices = [{ value: "", label: "(All)" }].concat((dashboard.regions || []).map(function (region) {
            return { value: region, label: region };
        }));
        var viewChoices = [
            { value: "country", label: "Country" },
            { value: "region", label: "Region" }
        ];
        tools.appendChild(selectControl("View by", "viewBy", viewChoices, "country"));
        tools.appendChild(selectControl("Region", "region", regionChoices, ""));

        var headline = el("div", "ppp-headline");
        var pillars = el("div", "ppp-pillars");
        var split = el("div", "ppp-split");
        var left = el("div");
        var right = el("div");
        left.appendChild(el("h2", "ppp-kicker", "PROGRAMME HIGHLIGHTS"));
        var highlightHost = el("div");
        left.appendChild(highlightHost);
        var mapHost = el("div", "ppp-map");
        mapHost.id = "ppp-map";
        var regionHost = el("ul", "ppp-region-list");
        right.appendChild(tools);
        right.appendChild(mapHost);
        right.appendChild(regionHost);
        split.appendChild(left);
        split.appendChild(right);
        var footnote = el("p", "ppp-footnote");

        stage.appendChild(headline);
        stage.appendChild(pillars);
        stage.appendChild(split);
        stage.appendChild(footnote);

        function paint() {
            filters.region = selected(tools.querySelector('[name="region"]'));
            filters.viewBy = selected(tools.querySelector('[name="viewBy"]'));
            var countries = filteredCountries(dashboard, filters);
            var reached = sumReached(countries);
            headline.replaceChildren();
            headline.appendChild(el("strong", "", compact(reached)));
            headline.appendChild(el("span", "", "people reached"));

            pillars.replaceChildren();
            (dashboard.pillars || []).forEach(function (pillar) {
                var card = el("article", "ppp-pillar");
                card.appendChild(icon(pillar.icon));
                card.appendChild(el("h2", "", pillar.title));
                card.appendChild(el("p", "", compact(sumKey(countries, "pillars", pillar.id))));
                pillars.appendChild(card);
            });

            highlightHost.replaceChildren();
            (dashboard.highlights || []).forEach(function (item) {
                var row = el("div", "ppp-highlight");
                row.appendChild(icon(item.icon));
                row.appendChild(el("p", "", item.title));
                row.appendChild(el("strong", "", full(sumKey(countries, "highlights", item.id))));
                highlightHost.appendChild(row);
            });

            var reporting = countries.filter(function (country) { return Number(country.reached) > 0; }).length;
            footnote.textContent = full(reached) + " people reached in " + reporting + " " + (reporting === 1 ? "country" : "countries");

            var showMap = filters.viewBy !== "region";
            mapHost.hidden = !showMap;
            regionHost.hidden = showMap;
            if (showMap) {
                drawMap(mapHost, countries);
            } else {
                if (map) {
                    map.remove();
                    map = null;
                }
                regionHost.replaceChildren();
                var byRegion = {};
                countries.forEach(function (country) {
                    var name = country.region || "Unspecified";
                    byRegion[name] = (byRegion[name] || 0) + (Number(country.reached) || 0);
                });
                Object.keys(byRegion).sort().forEach(function (name) {
                    var item = el("li");
                    item.appendChild(el("span", "", name));
                    item.appendChild(el("strong", "", full(byRegion[name])));
                    regionHost.appendChild(item);
                });
            }
        }

        tools.addEventListener("change", paint);
        paint();
    }

    function drawMap(host, countries) {
        if (!window.L) {
            host.replaceChildren(el("p", "ppp-state", "Map library did not load."));
            return;
        }
        if (map) {
            map.remove();
            map = null;
        }
        map = L.map(host, { scrollWheelZoom: false, attributionControl: true }).setView([12, 20], 2);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 8,
            attribution: "&copy; OpenStreetMap"
        }).addTo(map);
        var bounds = [];
        countries.forEach(function (country) {
            if (country.lat == null || country.lng == null) return;
            if (!(Number(country.reached) || Number(Object.values(country.pillars || {}).reduce(function (a, b) { return a + Number(b || 0); }, 0)))) return;
            var marker = L.circleMarker([country.lat, country.lng], {
                radius: 7,
                color: "#ffffff",
                weight: 2,
                fillColor: "#e30613",
                fillOpacity: 1
            }).addTo(map);
            marker.bindTooltip(country.name + " — " + full(country.reached));
            bounds.push([country.lat, country.lng]);
        });
        if (bounds.length) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 4 });
        setTimeout(function () { map.invalidateSize(); }, 0);
    }

    function renderDetail(dashboard, stage, filterSlot) {
        var filters = { region: "", country: "", pillar: "" };
        stage.classList.add("ppp-stage--detail");
        stage.replaceChildren();
        var bar = filterSlot || el("div", "ppp-filters");
        var regionChoices = [{ value: "", label: "(All)" }].concat((dashboard.regions || []).map(function (region) {
            return { value: region, label: region };
        }));
        var countryChoices = [{ value: "", label: "(All)" }].concat((dashboard.countries || []).map(function (country) {
            return { value: String(country.id), label: country.name };
        }));
        var pillarChoices = [{ value: "", label: "(All)" }].concat((dashboard.pillars || []).map(function (pillar) {
            return { value: pillar.id, label: pillar.title };
        }));
        bar.appendChild(selectControl("Region", "region", regionChoices, ""));
        bar.appendChild(selectControl("Country", "country", countryChoices, ""));
        bar.appendChild(selectControl("Pillar", "pillar", pillarChoices, ""));

        var headline = el("div", "ppp-headline");
        var grid = el("div", "ppp-detail");
        var left = el("div");
        var right = el("div");
        right.appendChild(el("h2", "ppp-section-title", "Activities"));
        var activityHost = el("div");
        right.appendChild(activityHost);
        grid.appendChild(left);
        grid.appendChild(right);
        if (!filterSlot) stage.appendChild(bar);
        stage.appendChild(headline);
        stage.appendChild(grid);

        function paint() {
            filters.region = selected(bar.querySelector('[name="region"]'));
            filters.country = selected(bar.querySelector('[name="country"]'));
            filters.pillar = selected(bar.querySelector('[name="pillar"]'));
            var countrySelect = bar.querySelector('[name="country"]');
            Array.prototype.forEach.call(countrySelect.options, function (node) {
                if (!node.value) return;
                var country = (dashboard.countries || []).find(function (item) { return String(item.id) === node.value; });
                node.hidden = !!(filters.region && country && country.region !== filters.region);
            });
            if (filters.country) {
                var current = (dashboard.countries || []).find(function (item) { return String(item.id) === String(filters.country); });
                if (current && filters.region && current.region !== filters.region) {
                    countrySelect.value = "";
                    filters.country = "";
                }
            }
            var countries = filteredCountries(dashboard, filters);
            var reached = sumReached(countries);
            headline.replaceChildren();
            headline.appendChild(el("strong", "", full(reached)));
            headline.appendChild(el("span", "", "people reached"));

            left.replaceChildren();
            var reachPanel = el("section", "ppp-panel");
            reachPanel.appendChild(el("h2", "", "People reached by pillar"));
            (dashboard.pillars || []).forEach(function (pillar) {
                var row = el("div", "ppp-reach-row");
                row.appendChild(icon(pillar.icon));
                var text = el("div");
                text.appendChild(el("strong", "", full(sumKey(countries, "pillars", pillar.id))));
                text.appendChild(el("span", "", "people reached by " + pillar.title));
                row.appendChild(text);
                reachPanel.appendChild(row);
            });
            left.appendChild(reachPanel);

            left.appendChild(el("h2", "ppp-section-title", "Indicators"));
            var table = el("table", "ppp-table");
            (dashboard.indicator_catalogue || []).forEach(function (indicator) {
                if (filters.pillar && indicator.pillar !== filters.pillar) return;
                var value = sumKey(countries, "indicators", indicator.id);
                var row = el("tr");
                row.appendChild(el("td", "", indicator.title));
                row.appendChild(el("td", "", indicator.kind === "yesno"
                    ? full(value) + (value === 1 ? " National Society" : " National Societies")
                    : full(value)));
                table.appendChild(row);
            });
            left.appendChild(table);

            activityHost.replaceChildren();
            var singleCountry = filters.country ? countries[0] : null;
            (dashboard.activity_catalogue || []).forEach(function (activity) {
                if (filters.pillar && activity.pillar !== filters.pillar) return;
                var block = el("article", "ppp-activity");
                block.appendChild(el("h3", "", activity.title));
                if (singleCountry) {
                    var answer = (singleCountry.activities || {})[activity.id] || {};
                    if (!answer.applicable && !answer.narrative) return;
                    if (answer.narrative) block.appendChild(el("p", "", answer.narrative));
                    else if (!answer.applicable) return;
                }
                activityHost.appendChild(block);
            });
        }

        bar.addEventListener("change", paint);
        paint();
    }

    function mount(dashboard, initialView) {
        root.replaceChildren();
        var toolbar = el("div", "ppp-toolbar");
        var toggle = el("div", "ppp-toggle");
        toggle.setAttribute("role", "tablist");
        toggle.setAttribute("aria-label", "Dashboard view");
        var buttons = {
            overview: el("button", "ppp-toggle__button", "Overview"),
            detail: el("button", "ppp-toggle__button", "Details")
        };
        Object.keys(buttons).forEach(function (name) {
            buttons[name].type = "button";
            buttons[name].setAttribute("role", "tab");
            buttons[name].addEventListener("click", function () { show(name); });
            toggle.appendChild(buttons[name]);
        });
        var filterSlot = el("div", "ppp-toolbar__filters");
        toolbar.appendChild(filterSlot);
        toolbar.appendChild(toggle);
        var stage = el("div", "ppp-stage");
        root.appendChild(toolbar);
        root.appendChild(stage);

        function show(next) {
            if (map) {
                map.remove();
                map = null;
            }
            var active = next === "detail" ? "detail" : "overview";
            buttons.overview.setAttribute("aria-selected", active === "overview" ? "true" : "false");
            buttons.detail.setAttribute("aria-selected", active === "detail" ? "true" : "false");
            filterSlot.replaceChildren();
            if (active === "detail") renderDetail(dashboard, stage, filterSlot);
            else renderOverview(dashboard, stage);
            var nextUrl = active === "detail" ? "?view=detail" : window.location.pathname;
            window.history.replaceState(null, "", nextUrl);
        }

        show(initialView === "detail" ? "detail" : "overview");
    }

    function showError() {
        root.replaceChildren(el("p", "ppp-state", "The programme figures could not be loaded."));
    }

    fetch(dataUrl, { headers: { "Accept": "application/json" } })
        .then(function (response) {
            if (!response.ok) throw new Error("load failed");
            return response.json();
        })
        .then(function (payload) {
            var dashboard = payload.dashboard || payload;
            if (!dashboard || !Array.isArray(dashboard.countries)) {
                showError();
                return;
            }
            if (!dashboard.countries.length) {
                root.replaceChildren(el("p", "ppp-state", "No approved Pilot Programmatic Partnership reports have been imported yet."));
                return;
            }
            mount(dashboard, view);
        })
        .catch(showError);
})();
