(function () {
    'use strict';

    var form = document.getElementById('dref-go-sync-form');
    if (!form) {
        return;
    }

    var startUrl = form.getAttribute('data-start-url');
    var statusTemplate = form.getAttribute('data-status-url') || '';
    var cancelTemplate = form.getAttribute('data-cancel-url') || '';
    var startFailed = form.getAttribute('data-msg-start-failed') || '';
    var statusFailed = form.getAttribute('data-msg-status-failed') || '';
    var panel = document.getElementById('dref-go-sync-status');
    var messageEl = document.getElementById('dref-go-sync-message');
    var bar = document.getElementById('dref-go-sync-bar');
    var meter = document.getElementById('dref-go-sync-meter');
    var countEl = document.getElementById('dref-go-sync-count');
    var startBtn = document.getElementById('dref-go-sync-start');
    var cancelBtn = document.getElementById('dref-go-sync-cancel');
    var settingsForm = document.querySelector('#panel-settings form');
    var currentUrl = form.getAttribute('data-current-url') || '';
    var external = form.getAttribute('data-external') === '1';
    var jobId = form.getAttribute('data-active-job') || '';
    var percentSeen = Number(form.getAttribute('data-active-percent') || 0);
    var timer = null;
    var misses = 0;
    var http = window.csrfFetch || window.fetch;

    function jobUrl(template, id) {
        return template.replace('__JOB__', encodeURIComponent(id));
    }

    function terminal(status) {
        return status === 'completed' || status === 'failed' || status === 'cancelled';
    }

    function render(payload) {
        if (!payload || !panel) {
            return;
        }
        panel.classList.remove('hidden');
        var pct = Number(payload.percent || 0);
        if (pct < percentSeen) {
            pct = percentSeen;
        }
        percentSeen = pct;
        var text = payload.status === 'failed' && payload.error ? payload.error : (payload.message || '');
        if (messageEl) {
            messageEl.textContent = text;
        }
        if (bar) {
            bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
        }
        if (meter) {
            meter.setAttribute('aria-valuenow', String(Math.round(pct)));
            meter.setAttribute('aria-valuetext', text);
        }
        if (countEl) {
            var bits = [];
            if (payload.total) {
                bits.push(String(payload.current || 0) + ' / ' + String(payload.total));
            }
            bits.push(Math.round(pct) + '%');
            countEl.textContent = bits.join(' · ');
        }
        var running = !terminal(payload.status);
        if (startBtn) {
            startBtn.disabled = running;
        }
        if (cancelBtn) {
            cancelBtn.classList.toggle('hidden', !running || !!payload.external);
            if (running) {
                cancelBtn.disabled = false;
            }
        }
    }

    function remember(payload) {
        var body = document.getElementById('dref-sync-history');
        if (!body || !payload) {
            return;
        }
        var empty = document.getElementById('dref-sync-history-empty');
        if (empty) {
            empty.remove();
        }
        var tr = document.createElement('tr');
        tr.className = 'border-t border-gray-200';
        var summary = payload.summary || {};
        var cells = [
            '-',
            '-',
            payload.status_label || payload.status || '',
            summary.created == null ? '-' : String(summary.created),
            summary.updated == null ? '-' : String(summary.updated),
            payload.message || payload.error || ''
        ];
        cells.forEach(function (value) {
            var td = document.createElement('td');
            td.className = 'px-3 py-2';
            td.textContent = value;
            tr.appendChild(td);
        });
        body.insertBefore(tr, body.firstChild);
    }

    function finish(payload) {
        if (timer) {
            window.clearTimeout(timer);
            timer = null;
        }
        if (payload.job_id) {
            remember(payload);
        }
        if (settingsForm && settingsForm.getAttribute('data-dirty') === '1') {
            return;
        }
        window.setTimeout(function () {
            var url = new URL(window.location.href);
            url.searchParams.set('tab', 'sync');
            window.location.assign(url.pathname + url.search);
        }, 800);
    }

    function poll() {
        if (!jobId && !external) {
            return;
        }
        http(jobId ? jobUrl(statusTemplate, jobId) : currentUrl, { headers: { Accept: 'application/json' } })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('status');
                }
                return response.json();
            })
            .then(function (payload) {
                misses = 0;
                render(payload);
                if (terminal(payload.status)) {
                    finish(payload);
                    return;
                }
                timer = window.setTimeout(poll, 1500);
            })
            .catch(function () {
                misses += 1;
                if (misses >= 4) {
                    if (messageEl) {
                        messageEl.textContent = statusFailed;
                    }
                    if (panel) {
                        panel.classList.remove('hidden');
                    }
                    if (startBtn) {
                        startBtn.disabled = false;
                    }
                    return;
                }
                timer = window.setTimeout(poll, 2000);
            });
    }

    if (settingsForm) {
        settingsForm.addEventListener('input', function () {
            settingsForm.setAttribute('data-dirty', '1');
        });
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        if (startBtn) {
            startBtn.disabled = true;
        }
        percentSeen = 0;
        misses = 0;
        http(startUrl, { method: 'POST', headers: { Accept: 'application/json' } })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('start');
                }
                return response.json();
            })
            .then(function (payload) {
                jobId = payload.job_id;
                external = false;
                render(payload);
                if (timer) {
                    window.clearTimeout(timer);
                }
                timer = window.setTimeout(poll, 400);
            })
            .catch(function () {
                if (startBtn) {
                    startBtn.disabled = false;
                }
                if (panel) {
                    panel.classList.remove('hidden');
                }
                if (messageEl) {
                    messageEl.textContent = startFailed;
                }
            });
    });

    if (cancelBtn) {
        cancelBtn.addEventListener('click', function () {
            if (!jobId) {
                return;
            }
            cancelBtn.disabled = true;
            http(jobUrl(cancelTemplate, jobId), { method: 'POST', headers: { Accept: 'application/json' } })
                .then(function () {
                    if (timer) {
                        window.clearTimeout(timer);
                    }
                    poll();
                })
                .catch(function () {
                    cancelBtn.disabled = false;
                });
        });
    }

    if (jobId || external) {
        poll();
    }
})();
