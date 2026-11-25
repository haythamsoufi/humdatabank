/* Report drafting buttons.
 *
 * 1. The dialogs on a DREF cycle's entry form, which pick how the report treats narrative.
 * 2. Draft forms (`form[data-dref-draft-form]`) on that dialog, the operation page and the
 *    draft page. An AI draft takes a minute or more, so the server queues it and this script
 *    polls the job and shows its progress. A draft without a model comes back at once.
 *    Without JavaScript the form posts normally and the server does the work in the request.
 */
(function () {
    'use strict';

    var controllers = {};
    var POLL_MS = 1500;
    var RETRY_MS = 2500;
    var MAX_MISSES = 4;
    var READ_DELAY_MS = 2500;

    function http(url, options) {
        var fn = window.csrfFetch || window.fetch;
        return fn.call(window, url, options);
    }

    function jobUrl(template, id) {
        return template.replace('__JOB__', encodeURIComponent(id));
    }

    function isTerminal(status) {
        return status === 'completed' || status === 'failed' || status === 'cancelled';
    }

    function readJson(response) {
        return response.json().then(
            function (body) {
                return { ok: response.ok, body: body || {} };
            },
            function () {
                return { ok: false, body: {} };
            }
        );
    }

    function initModals() {
        document.querySelectorAll('[data-dref-report-modal]').forEach(function (modal) {
            // Move the dialog to the page root so the header's layout cannot position or clip it.
            if (modal.parentElement !== document.body) {
                document.body.appendChild(modal);
            }
            controllers[modal.id] = window.ModalUtils
                ? window.ModalUtils.makeModal(modal, { closeSelector: '.close-modal' })
                : null;

            var form = modal.querySelector('[data-dref-report-form]');
            var submit = modal.querySelector('[data-dref-report-submit]');
            if (form && submit && !form.hasAttribute('data-dref-draft-form')) {
                form.addEventListener('submit', function () {
                    // One click makes one draft. The page navigates away when it is created.
                    submit.disabled = true;
                    var label = submit.getAttribute('data-loading-text');
                    if (label) {
                        submit.textContent = label;
                    }
                });
            }
        });

        document.querySelectorAll('[data-dref-report-open]').forEach(function (button) {
            button.addEventListener('click', function () {
                var id = button.getAttribute('data-dref-report-open');
                var controller = controllers[id];
                if (controller) {
                    controller.openModal();
                    var first = document.querySelector('#' + id + ' input[name="narrative"]:checked');
                    if (first) {
                        first.focus();
                    }
                }
            });
        });
    }

    function attachDraftForm(form) {
        var scope = form.closest('[data-dref-job-scope]') || form.parentElement;
        var panel = scope ? scope.querySelector('[data-dref-job-panel]') : null;
        if (!panel || form.getAttribute('data-dref-job-bound') === '1') {
            return;
        }
        form.setAttribute('data-dref-job-bound', '1');

        var statusTemplate = panel.getAttribute('data-status-url') || '';
        var cancelTemplate = panel.getAttribute('data-cancel-url') || '';
        var messageEl = panel.querySelector('[data-job-message]');
        var countEl = panel.querySelector('[data-job-count]');
        var bar = panel.querySelector('[data-job-bar]');
        var meter = panel.querySelector('[data-job-meter]');
        var hint = panel.querySelector('[data-job-hint]');
        var cancelBtn = panel.querySelector('[data-job-cancel]');
        var dotsEl = panel.querySelector('[data-job-dots]');
        var chaptersEl = panel.querySelector('[data-job-chapters]');
        var liveWrap = panel.querySelector('[data-job-live-wrap]');
        var liveEl = panel.querySelector('[data-job-live]');
        var liveTitle = panel.querySelector('[data-job-live-title]');
        var outline = {};
        try {
            outline = JSON.parse(panel.getAttribute('data-outline') || '{}') || {};
        } catch (error) {
            outline = {};
        }
        var state = { jobId: '', timer: null, misses: 0, percent: 0, busy: false, locked: [], kind: '', rows: {}, labels: {} };

        function say(text, failed) {
            if (messageEl) {
                messageEl.textContent = text || '';
                messageEl.classList.toggle('text-red-700', !!failed);
                messageEl.classList.toggle('text-purple-900', !failed);
            }
        }

        // One row per chapter of the report being drafted, so the page shows which one is being written.
        function buildChapters(kind) {
            var list = outline[kind] || outline.operational_update || [];
            if (!chaptersEl || !list.length || state.kind === kind) {
                return;
            }
            state.kind = kind;
            state.rows = {};
            state.labels = {};
            chaptersEl.textContent = '';
            list.forEach(function (chapter) {
                var row = document.createElement('li');
                row.className = 'dref-ai-chapter';
                var mark = document.createElement('span');
                mark.className = 'dref-ai-chapter__mark';
                mark.setAttribute('aria-hidden', 'true');
                var label = document.createElement('span');
                label.textContent = chapter.label;
                row.appendChild(mark);
                row.appendChild(label);
                chaptersEl.appendChild(row);
                state.rows[chapter.key] = row;
                state.labels[chapter.key] = chapter.label;
            });
            chaptersEl.classList.remove('hidden');
        }

        function markChapters(live, completed) {
            Object.keys(state.rows).forEach(function (key) {
                var row = state.rows[key];
                var done = completed || (live && (live.done || []).indexOf(key) >= 0);
                var writing = !done && live && live.writing === key;
                row.classList.toggle('is-done', !!done);
                row.classList.toggle('is-writing', !!writing);
            });
            if (!liveWrap || !liveEl) {
                return;
            }
            var showing = !completed && live && live.writing && live.text;
            liveWrap.classList.toggle('hidden', !showing);
            if (showing) {
                if (liveTitle) {
                    liveTitle.textContent = (panel.getAttribute('data-msg-writing') || '') + ' ' + (state.labels[live.writing] || '');
                }
                liveEl.textContent = live.text;
                liveEl.scrollTop = liveEl.scrollHeight;
            }
        }

        function render(payload) {
            panel.classList.remove('hidden');
            if (payload.kind) {
                buildChapters(payload.kind);
            }
            var pct = Number(payload.percent || 0);
            if (pct < state.percent && !isTerminal(payload.status)) {
                pct = state.percent;
            }
            state.percent = pct;
            var failed = payload.status === 'failed';
            var running = !isTerminal(payload.status);
            panel.classList.toggle('is-running', running);
            panel.classList.toggle('is-failed', failed);
            if (dotsEl) {
                dotsEl.classList.toggle('hidden', !running);
            }
            markChapters(payload.live, payload.status === 'completed');
            say(failed && payload.error ? payload.error : payload.message, failed);
            if (bar) {
                bar.style.width = Math.max(0, Math.min(100, pct)) + '%';
            }
            if (meter) {
                meter.setAttribute('aria-valuenow', String(Math.round(pct)));
                meter.setAttribute('aria-valuetext', messageEl ? messageEl.textContent : '');
            }
            if (countEl) {
                countEl.textContent = Math.round(pct) + '%';
            }
            if (cancelBtn) {
                cancelBtn.classList.toggle('hidden', !running);
                if (running && payload.status !== 'cancel_requested') {
                    cancelBtn.disabled = false;
                }
            }
            if (hint) {
                hint.classList.toggle('hidden', !running);
            }
        }

        function lock() {
            state.busy = true;
            state.locked = [];
            Array.prototype.forEach.call(form.elements, function (el) {
                if (el.disabled || el.closest('.close-modal') || el.classList.contains('close-modal')) {
                    return;
                }
                el.disabled = true;
                state.locked.push(el);
            });
        }

        function unlock() {
            state.busy = false;
            state.locked.forEach(function (el) {
                el.disabled = false;
            });
            state.locked = [];
        }

        function stopPolling() {
            if (state.timer) {
                window.clearTimeout(state.timer);
                state.timer = null;
            }
        }

        function fail(text) {
            stopPolling();
            panel.classList.remove('hidden');
            panel.classList.remove('is-running');
            panel.classList.add('is-failed');
            if (dotsEl) {
                dotsEl.classList.add('hidden');
            }
            if (liveWrap) {
                liveWrap.classList.add('hidden');
            }
            say(text, true);
            if (cancelBtn) {
                cancelBtn.classList.add('hidden');
            }
            if (hint) {
                hint.classList.add('hidden');
            }
            if (bar) {
                bar.style.width = '0%';
            }
            if (countEl) {
                countEl.textContent = '';
            }
            unlock();
        }

        function open(url, delay) {
            stopPolling();
            window.setTimeout(function () {
                window.location.assign(url);
            }, delay || 0);
        }

        function finish(payload) {
            stopPolling();
            render(payload);
            if (payload.status === 'completed' && payload.redirect_url) {
                var aiUsed = !payload.summary || payload.summary.ai_used !== false;
                if (!aiUsed) {
                    say(panel.getAttribute('data-msg-empty') || '', false);
                    open(payload.redirect_url, READ_DELAY_MS);
                } else {
                    // Let the last chapter tick off before the page changes.
                    open(payload.redirect_url, 900);
                }
                return;
            }
            // Failed or cancelled: show why and let the person try again.
            unlock();
        }

        function poll() {
            if (!state.jobId) {
                return;
            }
            http(jobUrl(statusTemplate, state.jobId), { headers: { Accept: 'application/json' } })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('status');
                    }
                    return response.json();
                })
                .then(function (payload) {
                    state.misses = 0;
                    if (isTerminal(payload.status)) {
                        finish(payload);
                        return;
                    }
                    render(payload);
                    state.timer = window.setTimeout(poll, POLL_MS);
                })
                .catch(function () {
                    state.misses += 1;
                    if (state.misses >= MAX_MISSES) {
                        fail(panel.getAttribute('data-msg-status-failed') || '');
                        return;
                    }
                    state.timer = window.setTimeout(poll, RETRY_MS);
                });
        }

        function follow(payload) {
            state.jobId = String(payload.job_id || '');
            state.misses = 0;
            render(payload);
            stopPolling();
            if (isTerminal(payload.status)) {
                finish(payload);
            } else {
                state.timer = window.setTimeout(poll, 400);
            }
        }

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (state.busy) {
                return;
            }
            // Read the fields before they are disabled, because a disabled field is not sent.
            var data = new FormData(form);
            lock();
            state.percent = 0;
            panel.classList.remove('is-failed');
            buildChapters(String(data.get('kind') || ''));
            markChapters(null, false);
            panel.classList.remove('hidden');
            render({ status: 'queued', message: messageEl ? messageEl.textContent : '', percent: 0 });
            http(form.getAttribute('action') || window.location.href, {
                method: 'POST',
                body: data,
                headers: { Accept: 'application/json' }
            })
                .then(readJson)
                .then(function (result) {
                    var body = result.body;
                    if (!result.ok) {
                        fail(body.error || panel.getAttribute('data-msg-start-failed') || '');
                        return;
                    }
                    if (body.job_id) {
                        follow(body);
                    } else if (body.redirect_url) {
                        // No model call: the draft already exists.
                        finish({ status: 'completed', percent: 100, redirect_url: body.redirect_url, summary: body.summary, message: '' });
                    } else {
                        fail(panel.getAttribute('data-msg-start-failed') || '');
                    }
                })
                .catch(function () {
                    fail(panel.getAttribute('data-msg-start-failed') || '');
                });
        });

        if (cancelBtn) {
            cancelBtn.addEventListener('click', function () {
                if (!state.jobId) {
                    return;
                }
                cancelBtn.disabled = true;
                say(panel.getAttribute('data-msg-cancelling') || '', false);
                http(jobUrl(cancelTemplate, state.jobId), { method: 'POST', headers: { Accept: 'application/json' } })
                    .then(function () {
                        stopPolling();
                        poll();
                    })
                    .catch(function () {
                        cancelBtn.disabled = false;
                    });
            });
        }

        // A reloaded page picks up the job it left running.
        var resumed = panel.getAttribute('data-active-job');
        if (resumed) {
            try {
                lock();
                follow(JSON.parse(resumed));
            } catch (error) {
                unlock();
            }
        }
    }

    function init() {
        initModals();
        document.querySelectorAll('form[data-dref-draft-form]').forEach(attachDraftForm);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
