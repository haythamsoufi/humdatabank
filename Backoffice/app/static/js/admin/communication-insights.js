/**
 * Communication Center insights tab — KPI refresh and Chart.js visuals.
 */
(function () {
    const CHART_COLORS = [
        'rgba(59, 130, 246, 0.88)',
        'rgba(16, 185, 129, 0.88)',
        'rgba(245, 158, 11, 0.88)',
        'rgba(239, 68, 68, 0.88)',
        'rgba(168, 85, 247, 0.88)',
        'rgba(100, 116, 139, 0.88)',
        'rgba(236, 72, 153, 0.88)',
        'rgba(14, 165, 233, 0.88)',
    ];

    const t = () => window.COMMUNICATION_TRANSLATIONS || {};

    function formatNumber(value) {
        const n = Number(value || 0);
        if (Number.isNaN(n)) return '0';
        return n.toLocaleString();
    }

    function setText(selector, value) {
        document.querySelectorAll(selector).forEach((el) => {
            el.textContent = value;
        });
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text != null) node.textContent = text;
        return node;
    }

    function clearNode(node) {
        while (node.firstChild) {
            node.removeChild(node.firstChild);
        }
    }

    function renderList(id, rows, emptyMessage, buildItem) {
        const list = document.getElementById(id);
        if (!list) return;
        clearNode(list);
        if (!rows || !rows.length) {
            list.appendChild(el('li', 'text-gray-500', emptyMessage));
            return;
        }
        rows.forEach((row) => {
            list.appendChild(buildItem(row));
        });
    }

    function labeledCountItem(label, countText) {
        const item = el('li', 'flex items-center justify-between gap-3');
        item.appendChild(el('span', 'text-gray-700', label));
        item.appendChild(el('span', 'font-medium text-gray-900', countText));
        return item;
    }

    function priorityItem(row) {
        const item = el('li', 'flex items-center justify-between gap-3');
        item.appendChild(el('span', 'text-gray-700', row.label));
        const value = el('span', 'font-medium text-gray-900', `${formatNumber(row.count)} `);
        value.appendChild(el('span', 'text-gray-500 font-normal', `(${formatNumber(row.read_rate)}%)`));
        item.appendChild(value);
        return item;
    }

    function destroyChart(charts, key) {
        if (charts[key]) {
            charts[key].destroy();
            delete charts[key];
        }
    }

    function chartDefaults() {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { boxWidth: 12, font: { size: 11 } } },
            },
        };
    }

    function renderDailyChart(charts, data) {
        if (typeof Chart === 'undefined') return;
        const canvas = document.getElementById('comms-insights-daily-chart');
        if (!canvas) return;
        destroyChart(charts, 'daily');
        const labels = (data.by_day || []).map((row) => row.date);
        const translations = t();
        charts.daily = new Chart(canvas.getContext('2d'), {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: translations.insightsDailyNotifications || 'Notifications',
                        data: (data.by_day || []).map((row) => row.notifications || 0),
                        backgroundColor: 'rgba(59, 130, 246, 0.85)',
                        stack: 'comms',
                    },
                    {
                        label: translations.insightsDailyEmails || 'Emails',
                        data: (data.by_day || []).map((row) => row.orphan_emails || 0),
                        backgroundColor: 'rgba(245, 158, 11, 0.85)',
                        stack: 'comms',
                    },
                ],
            },
            options: {
                ...chartDefaults(),
                scales: {
                    x: { stacked: true, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 12 } },
                    y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
                },
            },
        });
    }

    function renderDoughnut(charts, key, canvasId, rows, labelKey, valueKey) {
        if (typeof Chart === 'undefined') return;
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;
        destroyChart(charts, key);
        const items = (rows || []).filter((row) => (row[valueKey] || 0) > 0);
        charts[key] = new Chart(canvas.getContext('2d'), {
            type: 'doughnut',
            data: {
                labels: items.map((row) => row[labelKey]),
                datasets: [{
                    data: items.map((row) => row[valueKey] || 0),
                    backgroundColor: items.map((_, idx) => CHART_COLORS[idx % CHART_COLORS.length]),
                    borderWidth: 1,
                    borderColor: '#fff',
                }],
            },
            options: {
                ...chartDefaults(),
                plugins: {
                    legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } },
                },
            },
        });
    }

    function renderTypeTable(data) {
        const body = document.getElementById('comms-insights-type-body');
        if (!body) return;
        clearNode(body);
        const rows = data.by_type || [];
        if (!rows.length) {
            const tr = document.createElement('tr');
            const td = el('td', 'py-3 text-gray-500 text-center', t().insightsNoComms || 'No communications in this period.');
            td.colSpan = 3;
            tr.appendChild(td);
            body.appendChild(tr);
            return;
        }
        rows.forEach((row) => {
            const rate = row.type === 'email' ? (t().insightsReadRateNa || '—') : `${row.read_rate}%`;
            const tr = el('tr', 'border-t border-gray-100');
            tr.appendChild(el('td', 'py-1.5 pr-3 text-gray-800', row.label));
            tr.appendChild(el('td', 'py-1.5 pr-3 text-right text-gray-700', formatNumber(row.count)));
            tr.appendChild(el('td', 'py-1.5 text-right text-gray-700', rate));
            body.appendChild(tr);
        });
    }

    function renderKpis(data) {
        const totals = data.totals || {};
        const notifications = data.notifications || {};
        const email = data.email || {};
        const campaigns = data.campaigns || {};
        setText('[data-insight-kpi="communications"]', formatNumber(totals.communications));
        setText('[data-insight-kpi="notifications"]', formatNumber(totals.notifications));
        setText('[data-insight-kpi="orphan-emails"]', formatNumber(totals.orphan_emails));
        setText('[data-insight-kpi="today"]', formatNumber(totals.today));
        setText('[data-insight-kpi="avg-per-day"]', formatNumber(totals.avg_per_day));
        setText('[data-insight-kpi="unique-recipients"]', formatNumber(totals.unique_recipients));
        setText('[data-insight-kpi="read-rate"]', formatNumber(notifications.read_rate));
        setText('[data-insight-kpi="unread"]', formatNumber(notifications.unread));
        setText('[data-insight-kpi="read"]', formatNumber(notifications.read));
        setText('[data-insight-kpi="emails"]', formatNumber(email.total));
        setText('[data-insight-kpi="email-sent"]', formatNumber(email.sent));
        setText('[data-insight-kpi="email-attention"]', formatNumber(email.attention_needed));
        setText('[data-insight-kpi="campaigns"]', formatNumber(campaigns.total));
        setText('[data-insight-kpi="campaign-recipients"]', formatNumber(campaigns.sent_recipients));

        const periodLabel = document.getElementById('comms-insights-period-label');
        if (periodLabel) {
            const template = t().insightsPeriodLabel || 'Volume, types, and delivery for %(start)s to %(end)s.';
            periodLabel.textContent = template
                .replace('%(start)s', data.period_start || '—')
                .replace('%(end)s', data.period_end || '—');
        }

        const busiest = document.getElementById('comms-insights-busiest');
        if (busiest) {
            if (totals.busiest_day && totals.busiest_day.count) {
                busiest.classList.remove('hidden');
                setText('[data-insight-busiest-date]', totals.busiest_day.date || '');
                setText('[data-insight-busiest-count]', formatNumber(totals.busiest_day.count));
            } else {
                busiest.classList.add('hidden');
            }
        }
    }

    function renderAll(charts, data) {
        renderKpis(data);
        renderTypeTable(data);
        renderList(
            'comms-insights-channel-list',
            data.by_channel,
            t().insightsNoComms || 'No communications in this period.',
            (row) => labeledCountItem(row.label, formatNumber(row.count))
        );
        renderList(
            'comms-insights-email-list',
            (data.email && data.email.by_status) || [],
            t().insightsNoEmail || 'No email deliveries in this period.',
            (row) => labeledCountItem(row.label, formatNumber(row.count))
        );
        renderList(
            'comms-insights-priority-list',
            data.by_priority,
            t().insightsNoNotifications || 'No notifications in this period.',
            priorityItem
        );
        renderDailyChart(charts, data);
        renderDoughnut(charts, 'type', 'comms-insights-type-chart', data.by_type, 'label', 'count');
        renderDoughnut(charts, 'channel', 'comms-insights-channel-chart', data.by_channel, 'label', 'count');
        renderDoughnut(charts, 'email', 'comms-insights-email-chart', (data.email && data.email.by_status) || [], 'label', 'count');
        renderDoughnut(charts, 'priority', 'comms-insights-priority-chart', data.by_priority, 'label', 'count');
    }

    function resizeCharts(charts) {
        Object.keys(charts).forEach((key) => {
            if (charts[key] && typeof charts[key].resize === 'function') {
                charts[key].resize();
            }
        });
    }

    async function fetchInsights(days) {
        const cfg = window.communicationPageConfig || {};
        const url = new URL(cfg.urls && cfg.urls.communicationsInsights ? cfg.urls.communicationsInsights : '/admin/api/communications/insights', window.location.origin);
        url.searchParams.set('days', String(days));
        const fn = (window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch;
        const resp = await fn(url.toString(), { headers: { Accept: 'application/json' } });
        if (resp && typeof resp.json === 'function') {
            return resp.json();
        }
        return resp;
    }

    function createInsightsController() {
        const charts = {};
        let rendered = false;
        let loading = false;

        function currentDays() {
            const select = document.getElementById('comms-insights-days');
            return select ? select.value : '30';
        }

        function showError(message) {
            const el = document.getElementById('comms-insights-error');
            if (!el) return;
            if (!message) {
                el.classList.add('hidden');
                el.textContent = '';
                return;
            }
            el.textContent = message;
            el.classList.remove('hidden');
        }

        function setLoading(isLoading) {
            loading = isLoading;
            const el = document.getElementById('comms-insights-loading');
            if (el) {
                el.classList.toggle('hidden', !isLoading);
            }
        }

        function apply(data) {
            window.communicationInsights = data;
            renderAll(charts, data);
            rendered = true;
            requestAnimationFrame(() => resizeCharts(charts));
        }

        async function reload(days) {
            if (loading) return;
            setLoading(true);
            showError('');
            try {
                const payload = await fetchInsights(days);
                if (!payload || payload.success === false) {
                    throw new Error((payload && payload.error) || 'insights failed');
                }
                apply(payload);
            } catch (err) {
                console.error('Failed to load communication insights', err);
                showError(t().insightsLoadError || 'Could not load insights. Please try again.');
            } finally {
                setLoading(false);
            }
        }

        function onTabActivated() {
            if (!rendered && window.communicationInsights) {
                apply(window.communicationInsights);
            } else {
                resizeCharts(charts);
            }
        }

        function bind() {
            const select = document.getElementById('comms-insights-days');
            if (select && !select.dataset.insightsBound) {
                select.dataset.insightsBound = '1';
                select.addEventListener('change', () => reload(select.value));
            }
        }

        return {
            bind,
            onTabActivated,
            apply,
            reload,
            currentDays,
        };
    }

    window.CommunicationInsights = createInsightsController();

    document.addEventListener('DOMContentLoaded', () => {
        if (!window.CommunicationInsights) return;
        window.CommunicationInsights.bind();
    });
})();
