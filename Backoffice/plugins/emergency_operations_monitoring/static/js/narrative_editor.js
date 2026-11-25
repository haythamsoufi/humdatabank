/* Editing the chapters of a DREF draft.
 *
 * The same chapters appear twice on the draft page: as cards on the Narrative tab and in place in the
 * Preview, which looks like the Word file. Both are edited with TinyMCE in inline mode, share one
 * store, and stay in step. Changes save on their own a moment after typing stops.
 *
 * A chapter can be rewritten by the model. It runs as a background job; while it runs the chapter wears
 * the AI look (neon border, travelling spark, badge) and shows the text as it is written, then the new
 * text is typed in and can be undone. A Word file that was exported from the draft and edited can be
 * read back, and the person picks which chapters to take.
 *
 * Configuration comes from <script type="application/json" id="dref-narrative-config">.
 * Plugin scripts are not read by Tailwind, so every class used here is defined in the plugin CSS.
 */
(function () {
    'use strict';

    var configEl = document.getElementById('dref-narrative-config');
    if (!configEl) {
        return;
    }
    var cfg;
    try {
        cfg = JSON.parse(configEl.textContent || '{}');
    } catch (error) {
        return;
    }
    var L = cfg.labels || {};
    var SAVE_DELAY_MS = 1400;
    var RETRY_DELAY_MS = 4000;
    var POLL_MS = 1200;
    var MAX_MISSES = 4;
    var ALLOWED_TAGS = { P: 1, BR: 1, STRONG: 1, EM: 1, U: 1, S: 1, UL: 1, OL: 1, LI: 1, A: 1, SPAN: 1 };

    var chapters = {};
    var order = [];
    var views = [];
    var reducedMotion = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

    // ---- helpers ------------------------------------------------------------

    function fill(text, values) {
        return String(text || '').replace(/\{(\w+)\}/g, function (match, name) {
            return values && values[name] !== undefined ? values[name] : match;
        });
    }

    function http(url, options) {
        var fn = window.csrfFetch || window.fetch;
        return fn.call(window, url, options);
    }

    function readJson(response) {
        return response.json().then(
            function (body) {
                return { ok: response.ok, status: response.status, body: body || {} };
            },
            function () {
                return { ok: false, status: response.status, body: {} };
            }
        );
    }

    function postJson(url, body) {
        return http(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
            body: JSON.stringify(body || {})
        }).then(readJson);
    }

    function route(template, token, value) {
        return String(template || '').replace(token, encodeURIComponent(value));
    }

    function plainOf(html) {
        if (!html) {
            return '';
        }
        var text = html
            .replace(/<\/(p|li)>/gi, '\n')
            .replace(/<br\s*\/?>/gi, '\n')
            .replace(/<[^>]*>/g, '');
        var holder = document.createElement('textarea');
        holder.innerHTML = text;
        return holder.value.replace(/\u00a0/g, ' ').trim();
    }

    function wordsOf(text) {
        var found = text.match(/\S+/g);
        return found ? found.length : 0;
    }

    function safeHref(value) {
        var raw = String(value || '').replace(/^\s+|\s+$/g, '');
        if (!raw || raw.length > 2000 || /[\u0000-\u001f\s\\]/.test(raw)) {
            return '';
        }
        var lower = raw.toLowerCase();
        if (lower.indexOf('javascript:') === 0 || lower.indexOf('data:') === 0 || lower.indexOf('vbscript:') === 0) {
            return '';
        }
        if (!/^https?:\/\//i.test(raw) && !/^mailto:[^\s@]+@[^\s@]+$/i.test(raw.split('?')[0])) {
            return '';
        }
        return raw;
    }

    function copyStyle(from, to) {
        var color = from.style && from.style.color;
        var highlight = from.style && from.style.backgroundColor;
        if (color) {
            to.style.color = color;
        }
        if (highlight) {
            to.style.backgroundColor = highlight;
        }
        return !!(color || highlight);
    }

    // Copies the marks the chapter is allowed to keep. Anything else is unwrapped.
    function cleanInto(target, html) {
        target.textContent = '';
        var parsed = new DOMParser().parseFromString('<body>' + (html || '') + '</body>', 'text/html');
        (function copy(from, to) {
            Array.prototype.forEach.call(from.childNodes, function (node) {
                if (node.nodeType === 3) {
                    to.appendChild(document.createTextNode(node.nodeValue));
                } else if (node.nodeType === 1) {
                    var tag = node.tagName;
                    if (tag === 'B') {
                        tag = 'STRONG';
                    } else if (tag === 'I') {
                        tag = 'EM';
                    } else if (tag === 'STRIKE' || tag === 'DEL') {
                        tag = 'S';
                    }
                    if (!ALLOWED_TAGS[tag]) {
                        copy(node, to);
                        return;
                    }
                    if (tag === 'A' && !safeHref(node.getAttribute('href'))) {
                        copy(node, to);
                        return;
                    }
                    if (tag === 'SPAN' && !copyStyle(node, document.createElement('span'))) {
                        copy(node, to);
                        return;
                    }
                    var made = document.createElement(tag.toLowerCase());
                    if (tag === 'A') {
                        made.setAttribute('href', safeHref(node.getAttribute('href')));
                        made.setAttribute('target', '_blank');
                        made.setAttribute('rel', 'noopener noreferrer');
                    } else if (tag === 'SPAN') {
                        copyStyle(node, made);
                    }
                    to.appendChild(made);
                    if (tag !== 'BR') {
                        copy(node, made);
                    }
                }
            });
        })(parsed.body, target);
    }

    function show(el, on) {
        if (el) {
            el.classList.toggle('hidden', !on);
        }
    }

    function isTerminal(status) {
        return status === 'completed' || status === 'failed' || status === 'cancelled';
    }

    function copySources(rows) {
        return (rows || []).map(function (row) {
            return {
                id: row.id,
                chapter: row.chapter,
                kind: row.kind,
                title: row.title,
                date: row.date || '',
                locator: row.locator || '',
                url: row.url || '',
                used_for: row.used_for || ''
            };
        });
    }

    function sourcesDirty(st) {
        return JSON.stringify(st.sources || []) !== JSON.stringify(st.savedSources || []);
    }

    function publishSources() {
        if (!window.DrefSources) {
            return;
        }
        var all = [];
        order.forEach(function (key) {
            (chapters[key].sources || []).forEach(function (row) {
                all.push(row);
            });
        });
        window.DrefSources.set(all);
    }

    // ---- store --------------------------------------------------------------

    var initialSources = window.DrefSources ? window.DrefSources.list() : [];

    (cfg.chapters || []).forEach(function (row) {
        order.push(row.key);
        var mine = copySources(
            initialSources.filter(function (item) {
                return item.chapter === row.key;
            })
        );
        chapters[row.key] = {
            key: row.key,
            label: row.label,
            html: row.html || '',
            savedHtml: row.html || '',
            dirty: false,
            saving: false,
            again: false,
            pending: null,
            timer: null,
            retry: null,
            rejected: null,
            error: '',
            note: '',
            aiOriginal: !!row.aiOriginal,
            modelled: !!row.aiOriginal,
            edited: !!row.edited,
            sources: mine,
            savedSources: copySources(mine),
            generating: false,
            job: null,
            undo: null,
            words: row.words || 0,
            chars: row.chars || 0
        };
    });

    document.querySelectorAll('[data-chapter]').forEach(function (el) {
        var key = el.getAttribute('data-chapter');
        var body = el.querySelector('[data-chapter-body]');
        if (!chapters[key] || !body) {
            return;
        }
        views.push({
            key: key,
            el: el,
            body: body,
            area: el.getAttribute('data-area') || 'narrative',
            panel: el.closest('.settings-panel') || document,
            live: el.querySelector('[data-chapter-live]'),
            editor: null,
            starting: false,
            focusAfter: false,
            syncing: false
        });
    });

    function viewsOf(key) {
        return views.filter(function (view) {
            return view.key === key;
        });
    }

    // ---- display ------------------------------------------------------------

    function chipState(st) {
        if (st.generating) {
            return 'generating';
        }
        if (st.saving) {
            return 'saving';
        }
        if (st.error) {
            return 'error';
        }
        if (st.dirty) {
            return 'unsaved';
        }
        if (!st.html) {
            return 'empty';
        }
        if (st.aiOriginal) {
            return st.edited ? 'edited' : 'ai';
        }
        return st.edited ? 'edited' : 'written';
    }

    function chipText(state) {
        var chip = L.chip || {};
        var map = {
            empty: L.empty,
            written: L.written,
            ai: L.aiDraft,
            edited: L.edited,
            generating: chip.generating,
            saving: chip.saving,
            unsaved: chip.unsaved,
            error: chip.error
        };
        return map[state] || '';
    }

    function anyUnsaved() {
        return order.some(function (key) {
            var st = chapters[key];
            return st.dirty || st.saving || sourcesDirty(st);
        });
    }

    function refreshStatus() {
        var state = 'saved';
        var text = L.saved;
        var failing = order.some(function (key) {
            return chapters[key].error && !chapters[key].rejected;
        });
        var rejected = order.some(function (key) {
            return chapters[key].error && chapters[key].rejected;
        });
        if (failing) {
            state = 'error';
            text = L.saveFailed;
        } else if (rejected) {
            state = 'error';
            text = L.saveRejected;
        } else if (order.some(function (key) { return chapters[key].saving; })) {
            state = 'saving';
            text = L.saving;
        } else if (anyUnsaved()) {
            state = 'unsaved';
            text = L.unsaved;
        }
        document.querySelectorAll('[data-save-status]').forEach(function (el) {
            el.setAttribute('data-state', state);
            el.textContent = text || '';
        });
        var filled = order.filter(function (key) {
            return !!chapters[key].html;
        }).length;
        document.querySelectorAll('[data-progress-text]').forEach(function (el) {
            el.textContent = fill(L.progress, { done: filled, total: order.length });
        });
        document.querySelectorAll('[data-progress-bar]').forEach(function (el) {
            el.style.width = (order.length ? Math.round((filled / order.length) * 100) : 0) + '%';
        });
    }

    function refresh(st) {
        var text = plainOf(st.html);
        st.words = wordsOf(text);
        st.chars = text.length;
        var state = chipState(st);
        viewsOf(st.key).forEach(function (view) {
            if (view.area === 'narrative') {
                if (state === 'empty') {
                    view.el.setAttribute('data-vacant', '1');
                } else {
                    view.el.removeAttribute('data-vacant');
                }
            }
            var chip = view.el.querySelector('[data-chapter-chip]');
            if (chip) {
                chip.setAttribute('data-state', state);
                chip.textContent = chipText(state);
            }
            var count = view.el.querySelector('[data-chapter-count]');
            if (count) {
                count.textContent = fill(L.words, { n: st.words }) + ' \u00b7 ' + st.chars + ' / ' + cfg.limit;
                count.classList.toggle('is-over', st.chars > cfg.limit);
            }
            if (st.html) {
                view.body.removeAttribute('data-empty');
            } else if (!view.editor || !view.editor.hasFocus() || !view.body.textContent) {
                view.body.setAttribute('data-empty', '1');
            }
            var reset = view.el.querySelector('[data-act="reset"]');
            if (reset) {
                show(reset, st.aiOriginal && st.edited && !st.generating);
            }
            var sourcesBtn = view.el.querySelector('[data-act="sources"]');
            if (sourcesBtn) {
                var modelled = st.modelled || sourcesBtn.hasAttribute('data-sources-keep');
                show(sourcesBtn, !st.generating && !!plainOf(st.html) && (modelled || (st.sources || []).length > 0));
            }
            var rewrite = view.el.querySelector('[data-act="ai"]');
            if (rewrite) {
                rewrite.disabled = st.generating;
            }
            var failure = view.el.querySelector('[data-chapter-error]');
            if (failure) {
                failure.textContent = st.error || st.note || '';
                show(failure, !!(st.error || st.note));
            }
        });
        document.querySelectorAll('[data-nav-chapter="' + st.key + '"]').forEach(function (link) {
            link.setAttribute('data-state', state);
        });
        refreshStatus();
    }

    // ---- editors ------------------------------------------------------------

    var tinyLoad = null;

    function loadTiny(done) {
        if (window.tinymce) {
            window.setTimeout(function () {
                done(true);
            }, 0);
            return;
        }
        if (!tinyLoad) {
            tinyLoad = new Promise(function (resolve) {
                var script = document.createElement('script');
                script.src = cfg.tinymceBase + '/tinymce.min.js';
                script.onload = function () {
                    resolve(true);
                };
                script.onerror = function () {
                    resolve(false);
                };
                document.head.appendChild(script);
            });
        }
        tinyLoad.then(done);
    }

    function htmlOf(editor) {
        var text = editor.getContent({ format: 'text' }).replace(/\u00a0/g, ' ').trim();
        // TinyMCE puts a line break between blocks; the server writes none. Without this every focus
        // would look like an edit.
        return text ? editor.getContent().replace(/>\s*\n\s*</g, '><').trim() : '';
    }

    var blurTimers = new WeakMap();

    function setActive(view, on) {
        var bar = view.panel.querySelector ? view.panel.querySelector('[data-editbar]') : null;
        if (!bar) {
            return;
        }
        window.clearTimeout(blurTimers.get(bar));
        if (on) {
            bar.setAttribute('data-active', '1');
            return;
        }
        blurTimers.set(
            bar,
            window.setTimeout(function () {
                bar.setAttribute('data-active', '0');
            }, 250)
        );
    }

    function editorOptions(view, slot) {
        var toolbar = 'undo redo | bold italic underline strikethrough | forecolor backcolor | link | bullist numlist | removeformat';
        if (cfg.aiReady) {
            toolbar += ' | airewrite';
        }
        return {
            target: view.body,
            inline: true,
            license_key: 'gpl',
            base_url: cfg.tinymceBase,
            suffix: '.min',
            skin: 'oxide',
            content_css: false,
            menubar: false,
            statusbar: false,
            branding: false,
            promotion: false,
            plugins: 'lists link autolink',
            toolbar: toolbar,
            toolbar_mode: 'wrap',
            fixed_toolbar_container_target: slot || undefined,
            valid_elements: 'p,br,strong/b,em/i,u,s/strike/del,span[style],a[href|target|rel],ul,ol,li',
            valid_styles: { span: 'color,background-color' },
            link_default_target: '_blank',
            link_assume_external_targets: 'https',
            formats: {
                bold: { inline: 'strong' },
                italic: { inline: 'em' },
                underline: { inline: 'u', exact: true },
                strikethrough: { inline: 's', exact: true }
            },
            forced_root_block: 'p',
            lists_indent_on_tab: false,
            entity_encoding: 'raw',
            browser_spellcheck: true,
            paste_data_images: false,
            convert_urls: false,
            directionality: cfg.rtl ? 'rtl' : 'ltr',
            setup: function (editor) {
                editor.on('input change keyup undo redo ExecCommand', function () {
                    changed(view);
                });
                editor.on('focus', function () {
                    setActive(view, true);
                    view.body.removeAttribute('data-empty');
                });
                editor.on('blur', function () {
                    setActive(view, false);
                    refresh(chapters[view.key]);
                });
                editor.on('keydown', function (event) {
                    if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === 's') {
                        event.preventDefault();
                        saveNow(view.key);
                    }
                });
                if (cfg.aiReady && editor.ui && editor.ui.registry) {
                    editor.ui.registry.addButton('airewrite', {
                        icon: 'ai',
                        text: L.rewrite,
                        tooltip: L.rewrite,
                        onAction: function () {
                            toggleAi(view.key, view.area);
                        }
                    });
                }
            },
            init_instance_callback: function (editor) {
                view.editor = editor;
                view.starting = false;
                var spellcheck = editor.getBody();
                if (spellcheck) {
                    spellcheck.setAttribute('spellcheck', 'true');
                }
                if (chapters[view.key].generating) {
                    editor.mode.set('readonly');
                } else if (view.focusAfter) {
                    editor.focus();
                }
                view.focusAfter = false;
            }
        };
    }

    function ensureEditor(view, focus) {
        if (!cfg.canEdit) {
            return;
        }
        if (view.editor) {
            if (focus && !chapters[view.key].generating) {
                view.editor.focus();
            }
            return;
        }
        if (view.starting) {
            view.focusAfter = view.focusAfter || !!focus;
            return;
        }
        view.starting = true;
        view.focusAfter = !!focus;
        loadTiny(function (ok) {
            if (!ok || !window.tinymce) {
                view.starting = false;
                return;
            }
            var slot = view.panel.querySelector ? view.panel.querySelector('[data-toolbar-slot]') : null;
            try {
                window.tinymce.init(editorOptions(view, slot));
            } catch (error) {
                view.starting = false;
            }
        });
    }

    var initQueue = [];
    var initTimer = null;

    function pump() {
        initTimer = null;
        var view = initQueue.shift();
        if (!view) {
            return;
        }
        ensureEditor(view, false);
        initTimer = window.setTimeout(pump, 40);
    }

    function initPanel(panel) {
        if (!panel) {
            return;
        }
        views.forEach(function (view) {
            if (view.panel === panel && !view.editor && !view.starting && initQueue.indexOf(view) < 0) {
                initQueue.push(view);
            }
        });
        if (!initTimer) {
            initTimer = window.setTimeout(pump, 0);
        }
    }

    function visiblePanel() {
        var found = null;
        document.querySelectorAll('#dref-draft-panels .settings-panel').forEach(function (panel) {
            if (!panel.classList.contains('hidden')) {
                found = panel;
            }
        });
        return found;
    }

    function setViewHtml(view, html) {
        view.syncing = true;
        try {
            if (view.editor) {
                view.editor.setContent(html || '');
            } else {
                cleanInto(view.body, html);
            }
        } finally {
            view.syncing = false;
        }
        if (plainOf(html)) {
            view.body.removeAttribute('data-empty');
        } else {
            view.body.setAttribute('data-empty', '1');
        }
        if (window.DrefEmptySections) {
            window.DrefEmptySections.sync(view.body.closest('.dref-chapter--inline'), !!plainOf(html));
        }
    }

    function setAllViews(st, html, except) {
        viewsOf(st.key).forEach(function (view) {
            if (view !== except) {
                setViewHtml(view, html);
            }
        });
    }

    function changed(view) {
        var st = chapters[view.key];
        if (!view.editor || view.syncing || st.generating) {
            return;
        }
        var html = htmlOf(view.editor);
        if (html === st.html) {
            return;
        }
        st.html = html;
        st.dirty = html !== st.savedHtml;
        st.error = '';
        st.note = '';
        st.rejected = null;
        st.edited = st.aiOriginal ? true : st.edited;
        hideUndo(st);
        setAllViews(st, html, view);
        if (window.DrefEmptySections) {
            window.DrefEmptySections.sync(
                document.querySelector('.dref-chapter--inline[data-chapter="' + view.key + '"]'),
                !!plainOf(html)
            );
        }
        refresh(st);
        schedule(st);
    }

    // ---- saving -------------------------------------------------------------

    function schedule(st) {
        window.clearTimeout(st.timer);
        if (!st.dirty) {
            return;
        }
        st.timer = window.setTimeout(function () {
            save(st);
        }, SAVE_DELAY_MS);
    }

    function saveNow(key) {
        var st = chapters[key];
        window.clearTimeout(st.timer);
        return save(st);
    }

    function save(st) {
        window.clearTimeout(st.timer);
        window.clearTimeout(st.retry);
        if (st.generating) {
            return Promise.resolve(true);
        }
        if (st.saving) {
            st.again = true;
            return st.pending || Promise.resolve(false);
        }
        if (st.html === st.savedHtml && !sourcesDirty(st)) {
            st.dirty = false;
            refresh(st);
            return Promise.resolve(true);
        }
        if (st.rejected !== null && st.rejected === st.html) {
            return Promise.resolve(false);
        }
        var sent = st.html;
        var sentSources = sourcesDirty(st) ? copySources(st.sources) : null;
        var sections = {};
        sections[st.key] = sent;
        var body = { sections: sections };
        if (sentSources) {
            body.sources = {};
            body.sources[st.key] = sentSources;
        }
        st.saving = true;
        st.error = '';
        refresh(st);
        st.pending = postJson(cfg.saveUrl, body)
            .then(function (result) {
                st.saving = false;
                var saved = result.body.saved && result.body.saved[st.key];
                var failed = result.body.failed && result.body.failed[st.key];
                if (saved) {
                    st.savedHtml = sent;
                    if (sentSources && JSON.stringify(st.sources) === JSON.stringify(sentSources)) {
                        st.savedSources = sentSources;
                    }
                    st.rejected = null;
                    st.error = '';
                } else if (failed || (result.status >= 400 && result.status < 500 && result.body.error)) {
                    st.rejected = sent;
                    st.error = failed || result.body.error || L.saveRejected;
                } else {
                    st.error = L.saveFailed;
                    st.retry = window.setTimeout(function () {
                        save(st);
                    }, RETRY_DELAY_MS);
                }
                st.dirty = st.html !== st.savedHtml || sourcesDirty(st);
                refresh(st);
                if (saved && st.dirty) {
                    schedule(st);
                }
                return !!saved;
            })
            .catch(function () {
                st.saving = false;
                st.error = L.saveFailed;
                st.retry = window.setTimeout(function () {
                    save(st);
                }, RETRY_DELAY_MS);
                refresh(st);
                return false;
            });
        return st.pending;
    }

    function flushAll() {
        var jobs = order
            .map(function (key) {
                return chapters[key];
            })
            .filter(function (st) {
                return st.dirty || st.saving || sourcesDirty(st);
            })
            .map(function (st) {
                if (st.saving && st.pending) {
                    return st.pending.then(function () {
                        return st.dirty ? save(st) : true;
                    });
                }
                return saveNow(st.key);
            });
        return Promise.all(jobs).then(function (results) {
            return results.every(Boolean) && !anyUnsaved();
        });
    }

    window.addEventListener('beforeunload', function (event) {
        if (anyUnsaved()) {
            event.preventDefault();
            event.returnValue = L.leave || '';
        }
    });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden' && anyUnsaved()) {
            flushAll();
        }
    });

    document.querySelectorAll('form[data-dref-flush]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!anyUnsaved()) {
                return;
            }
            event.preventDefault();
            var button = form.querySelector('button[type="submit"]');
            if (button) {
                button.disabled = true;
            }
            flushAll().then(function (ok) {
                if (button) {
                    button.disabled = false;
                }
                if (ok) {
                    form.submit();
                }
            });
        });
    });

    // ---- undo notice --------------------------------------------------------

    function showUndo(st, text) {
        viewsOf(st.key).forEach(function (view) {
            var bar = view.el.querySelector('[data-chapter-undo]');
            var label = view.el.querySelector('[data-chapter-undo-text]');
            if (label) {
                label.textContent = text;
            }
            show(bar, true);
        });
    }

    function hideUndo(st) {
        st.undo = null;
        viewsOf(st.key).forEach(function (view) {
            show(view.el.querySelector('[data-chapter-undo]'), false);
        });
    }

    function applyText(st, html, edited) {
        st.html = html;
        st.edited = edited;
        st.dirty = st.html !== st.savedHtml || sourcesDirty(st);
        st.error = '';
        st.rejected = null;
        setAllViews(st, html, null);
        refresh(st);
    }

    function undoChange(st) {
        if (!st.undo || st.generating) {
            return;
        }
        var back = st.undo;
        hideUndo(st);
        st.sources = copySources(back.sources);
        applyText(st, back.html, back.edited);
        publishSources();
        saveNow(st.key);
    }

    // ---- the model writing a chapter ----------------------------------------

    function setGenerating(st, on, message) {
        st.generating = on;
        viewsOf(st.key).forEach(function (view) {
            view.el.classList.toggle('dref-ai-active', on);
            view.el.classList.toggle('is-generating', on);
            show(view.el.querySelector('[data-chapter-badge]'), on);
            var text = view.el.querySelector('[data-chapter-badge-text]');
            if (text && message) {
                text.textContent = message;
            }
            if (view.live) {
                view.live.classList.remove('is-typed');
                view.live.classList.toggle('dref-ai-caret', on);
                show(view.live, on);
                if (on) {
                    view.live.textContent = '';
                }
            }
            if (view.editor) {
                view.editor.mode.set(on ? 'readonly' : 'design');
            }
            var cancel = view.el.querySelector('[data-act="cancel-ai"]');
            if (cancel) {
                cancel.disabled = false;
            }
            closeAi(view);
        });
        refresh(st);
    }

    function renderJob(st, payload) {
        var text = payload.live && payload.live.text ? payload.live.text : '';
        viewsOf(st.key).forEach(function (view) {
            var badge = view.el.querySelector('[data-chapter-badge-text]');
            if (badge && payload.status !== 'cancel_requested') {
                badge.textContent = payload.message || L.badge;
            }
            if (view.live && text) {
                view.live.textContent = text;
                view.live.scrollTop = view.live.scrollHeight;
            }
        });
    }

    function stopJob(st) {
        if (st.job && st.job.timer) {
            window.clearTimeout(st.job.timer);
        }
    }

    function failRewrite(st, message) {
        stopJob(st);
        st.job = null;
        setGenerating(st, false);
        st.note = message || L.rewriteFailed;
        refresh(st);
    }

    // Types the new text into the chapter, then hands it to the editors and saves it.
    function typeIn(st, html, previous, incoming) {
        var targets = viewsOf(st.key)
            .map(function (view) {
                return view.live;
            })
            .filter(Boolean);
        var runs = targets.map(function (target) {
            cleanInto(target, html);
            target.classList.add('is-typed');
            target.classList.remove('dref-ai-caret');
            var nodes = [];
            (function walk(node) {
                Array.prototype.forEach.call(node.childNodes, function (child) {
                    if (child.nodeType === 3) {
                        child._full = child.nodeValue;
                        child.nodeValue = '';
                        nodes.push(child);
                    } else {
                        walk(child);
                    }
                });
            })(target);
            return nodes;
        });
        var total = (runs[0] || []).reduce(function (sum, node) {
            return sum + node._full.length;
        }, 0);
        var duration = reducedMotion ? 0 : Math.max(500, Math.min(2200, total * 6));
        var started = null;

        function finish() {
            var prior = {
                html: previous.html,
                edited: previous.edited,
                sources: copySources(previous.sources)
            };
            st.sources = copySources(incoming);
            if (plainOf(html)) {
                st.modelled = true;
            }
            setGenerating(st, false);
            applyText(st, html, true);
            st.undo = prior;
            showUndo(st, L.rewriteDone);
            publishSources();
            saveNow(st.key);
        }

        function frame(now) {
            if (started === null) {
                started = now;
            }
            var progress = duration ? Math.min(1, (now - started) / duration) : 1;
            var upto = Math.floor(total * progress);
            runs.forEach(function (nodes) {
                var left = upto;
                nodes.forEach(function (node) {
                    var take = Math.max(0, Math.min(node._full.length, left));
                    node.nodeValue = node._full.slice(0, take);
                    left -= take;
                });
            });
            if (progress < 1) {
                window.requestAnimationFrame(frame);
            } else {
                window.setTimeout(finish, 250);
            }
        }

        window.requestAnimationFrame(frame);
    }

    function finishJob(st, payload, previous) {
        stopJob(st);
        st.job = null;
        if (payload.status === 'completed') {
            var html = payload.summary && payload.summary.html ? String(payload.summary.html) : '';
            if (html) {
                var incoming = payload.summary && Array.isArray(payload.summary.sources) ? payload.summary.sources : [];
                typeIn(
                    st,
                    html,
                    previous,
                    incoming.filter(function (row) {
                        return row && row.chapter === st.key;
                    })
                );
                return;
            }
            failRewrite(st, L.rewriteFailed);
            return;
        }
        failRewrite(st, payload.status === 'cancelled' ? L.rewriteCancelled : payload.error || L.rewriteFailed);
    }

    function follow(st, payload, previous) {
        st.job = { id: String(payload.job_id || ''), misses: 0, timer: null };
        renderJob(st, payload);
        if (isTerminal(payload.status)) {
            finishJob(st, payload, previous);
            return;
        }

        function poll() {
            if (!st.job) {
                return;
            }
            http(route(cfg.statusUrl, '__JOB__', st.job.id), { headers: { Accept: 'application/json' } })
                .then(function (response) {
                    if (!response.ok) {
                        throw new Error('status');
                    }
                    return response.json();
                })
                .then(function (body) {
                    if (!st.job) {
                        return;
                    }
                    st.job.misses = 0;
                    if (isTerminal(body.status)) {
                        finishJob(st, body, previous);
                        return;
                    }
                    renderJob(st, body);
                    st.job.timer = window.setTimeout(poll, POLL_MS);
                })
                .catch(function () {
                    if (!st.job) {
                        return;
                    }
                    st.job.misses += 1;
                    if (st.job.misses >= MAX_MISSES) {
                        failRewrite(st, L.rewriteFailed);
                        return;
                    }
                    st.job.timer = window.setTimeout(poll, POLL_MS * 2);
                });
        }

        st.job.timer = window.setTimeout(poll, 500);
    }

    function startRewrite(key, instruction) {
        var st = chapters[key];
        if (!st || st.generating) {
            return;
        }
        // Take what is typed into the store first, so the model reads the latest text.
        viewsOf(key).forEach(function (view) {
            if (view.editor && view.editor.hasFocus()) {
                changed(view);
            }
        });
        var previous = { html: st.html, edited: st.edited, sources: copySources(st.sources) };
        hideUndo(st);
        st.error = '';
        st.note = '';
        setGenerating(st, true, L.badge);
        postJson(route(cfg.generateUrl, '__KEY__', key), { instruction: instruction, current: st.html })
            .then(function (result) {
                if (!result.ok || !result.body.job_id) {
                    failRewrite(st, result.body.error || L.rewriteFailed);
                    return;
                }
                follow(st, result.body, previous);
            })
            .catch(function () {
                failRewrite(st, L.rewriteFailed);
            });
    }

    function cancelRewrite(st) {
        if (!st.job) {
            return;
        }
        viewsOf(st.key).forEach(function (view) {
            var badge = view.el.querySelector('[data-chapter-badge-text]');
            if (badge) {
                badge.textContent = L.badgeCancelling;
            }
            var cancel = view.el.querySelector('[data-act="cancel-ai"]');
            if (cancel) {
                cancel.disabled = true;
            }
        });
        http(route(cfg.cancelUrl, '__JOB__', st.job.id), { method: 'POST', headers: { Accept: 'application/json' } }).catch(
            function () {
                return null;
            }
        );
    }

    // ---- the rewrite form ---------------------------------------------------

    function closeAi(view) {
        var slot = view.el.querySelector('[data-chapter-ai-slot]');
        if (slot) {
            slot.textContent = '';
        }
    }

    function toggleAi(key, area) {
        var st = chapters[key];
        if (!st || st.generating) {
            return;
        }
        var view =
            views.filter(function (item) {
                return item.key === key && item.area === area;
            })[0] || viewsOf(key)[0];
        var slot = view && view.el.querySelector('[data-chapter-ai-slot]');
        var template = document.getElementById('dref-ai-template');
        if (!slot || !template) {
            return;
        }
        if (slot.firstChild) {
            slot.textContent = '';
            return;
        }
        var form = template.content.firstElementChild.cloneNode(true);
        form.querySelector('[data-ai-instruction-label]').textContent = L.aiInstruction || '';
        var input = form.querySelector('[data-ai-instruction]');
        input.setAttribute('placeholder', L.instructionPlaceholder || '');
        form.querySelector('[data-ai-caution]').textContent = L.aiCaution || '';
        var cancel = form.querySelector('[data-ai-cancel]');
        var run = form.querySelector('[data-ai-run]');
        cancel.textContent = L.aiCancel || '';
        run.textContent = L.aiRun || '';
        var chipHost = form.querySelector('[data-ai-chips]');
        ((L.chips && L.chips.ai) || []).forEach(function (chip) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'dref-tool';
            button.textContent = chip.label;
            button.addEventListener('click', function () {
                input.value = (input.value ? input.value.replace(/\s+$/, '') + ' ' : '') + chip.text;
                input.focus();
            });
            chipHost.appendChild(button);
        });
        cancel.addEventListener('click', function () {
            slot.textContent = '';
        });
        run.addEventListener('click', function () {
            var instruction = input.value;
            slot.textContent = '';
            startRewrite(key, instruction);
        });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                slot.textContent = '';
            } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                run.click();
            }
        });
        slot.appendChild(form);
        input.focus();
        if (view.el.scrollIntoView) {
            view.el.scrollIntoView({ block: 'nearest', behavior: reducedMotion ? 'auto' : 'smooth' });
        }
    }

    // ---- back to the model's text -------------------------------------------

    function resetChapter(st) {
        if (st.generating || !st.aiOriginal) {
            return;
        }
        var previous = { html: st.html, edited: st.edited, sources: copySources(st.sources) };
        window.clearTimeout(st.timer);
        st.error = '';
        st.note = '';
        postJson(route(cfg.resetUrl, '__KEY__', st.key), {})
            .then(function (result) {
                if (!result.ok || !result.body.ok) {
                    st.note = result.body.error || L.resetFailed;
                    refresh(st);
                    return;
                }
                st.savedHtml = result.body.html || '';
                st.sources = copySources(result.body.sources);
                st.savedSources = copySources(st.sources);
                applyText(st, st.savedHtml, false);
                st.undo = previous;
                publishSources();
                showUndo(st, L.resetDone);
            })
            .catch(function () {
                st.note = L.resetFailed;
                refresh(st);
            });
    }

    // ---- clicks on chapters -------------------------------------------------

    document.addEventListener('click', function (event) {
        var button = event.target.closest ? event.target.closest('[data-act]') : null;
        if (!button) {
            return;
        }
        var host = button.closest('[data-chapter]');
        var st = host ? chapters[host.getAttribute('data-chapter')] : null;
        var act = button.getAttribute('data-act');
        if (act === 'ai' && st) {
            toggleAi(st.key, host.getAttribute('data-area'));
        } else if (act === 'reset' && st) {
            resetChapter(st);
        } else if (act === 'undo' && st) {
            undoChange(st);
        } else if (act === 'keep' && st) {
            hideUndo(st);
        } else if (act === 'cancel-ai' && st) {
            cancelRewrite(st);
        }
    });

    views.forEach(function (view) {
        view.body.setAttribute('tabindex', '0');
        view.body.addEventListener('pointerdown', function () {
            ensureEditor(view, true);
        });
        view.body.addEventListener('focus', function () {
            ensureEditor(view, true);
        });
    });

    // ---- chapter list -------------------------------------------------------

    document.querySelectorAll('[data-nav-chapter]').forEach(function (link) {
        link.addEventListener('click', function () {
            var key = link.getAttribute('data-nav-chapter');
            var card = document.getElementById('chapter-' + key);
            if (card && card.scrollIntoView) {
                card.scrollIntoView({ block: 'start', behavior: reducedMotion ? 'auto' : 'smooth' });
            }
            var view = views.filter(function (item) {
                return item.key === key && item.area === 'narrative';
            })[0];
            if (view) {
                window.setTimeout(function () {
                    ensureEditor(view, true);
                }, reducedMotion ? 0 : 350);
            }
        });
    });

    if ('IntersectionObserver' in window) {
        var currentKey = '';
        var observer = new IntersectionObserver(
            function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        currentKey = entry.target.getAttribute('data-chapter');
                        document.querySelectorAll('[data-nav-chapter]').forEach(function (link) {
                            link.classList.toggle('is-current', link.getAttribute('data-nav-chapter') === currentKey);
                        });
                    }
                });
            },
            { rootMargin: '-15% 0px -65% 0px', threshold: 0 }
        );
        views.forEach(function (view) {
            if (view.area === 'narrative') {
                observer.observe(view.el);
            }
        });
    }

    // ---- Word import --------------------------------------------------------

    function initImport() {
        var modal = document.getElementById('dref-import-modal');
        if (!modal) {
            return;
        }
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        var controller = window.ModalUtils ? window.ModalUtils.makeModal(modal, { closeSelector: '.close-modal' }) : null;
        var steps = {};
        modal.querySelectorAll('[data-import-step]').forEach(function (step) {
            steps[step.getAttribute('data-import-step')] = step;
        });
        var fileInput = modal.querySelector('[data-import-file]');
        var errorEl = modal.querySelector('[data-import-error]');
        var analyze = modal.querySelector('[data-import-analyze]');
        var summaryEl = modal.querySelector('[data-import-summary]');
        var warningsEl = modal.querySelector('[data-import-warnings]');
        var listEl = modal.querySelector('[data-import-list]');
        var ignoredEl = modal.querySelector('[data-import-ignored]');
        var applyBtn = modal.querySelector('[data-import-apply]');
        var doneEl = modal.querySelector('[data-import-done]');
        var undoBtn = modal.querySelector('[data-import-undo]');
        var rowTemplate = document.getElementById('dref-import-row');
        var result = null;
        var before = {};

        function step(name) {
            Object.keys(steps).forEach(function (key) {
                show(steps[key], key === name);
            });
        }

        function fail(message) {
            if (errorEl) {
                errorEl.textContent = message || L.importFailed;
                show(errorEl, true);
            }
        }

        function statusLabel(status) {
            return {
                changed: L.statusChanged,
                added: L.statusAdded,
                cleared: L.statusCleared,
                unchanged: L.statusUnchanged,
                missing: L.statusMissing,
                too_long: L.statusTooLong
            }[status] || status;
        }

        function open() {
            step('pick');
            show(errorEl, false);
            if (fileInput) {
                fileInput.value = '';
            }
            result = null;
            if (controller) {
                controller.openModal();
            }
        }

        function review(data) {
            result = data;
            var actionable = (data.chapters || []).filter(function (row) {
                return ['changed', 'added', 'cleared', 'too_long'].indexOf(row.status) >= 0;
            });
            listEl.textContent = '';
            actionable.forEach(function (row) {
                var item = rowTemplate.content.firstElementChild.cloneNode(true);
                var check = item.querySelector('[data-row-check]');
                check.setAttribute('data-key', row.key);
                check.checked = row.status === 'changed' || row.status === 'added';
                check.disabled = row.status === 'too_long' || !!(chapters[row.key] && chapters[row.key].generating);
                item.querySelector('[data-row-label]').textContent = row.label;
                var badge = item.querySelector('[data-row-status]');
                badge.textContent = statusLabel(row.status);
                badge.setAttribute('data-status', row.status);
                item.querySelector('[data-row-words]').textContent = fill(L.words, {
                    n: row.words_before + ' \u2192 ' + row.words_after
                });
                item.querySelector('[data-row-current]').textContent = row.current || '';
                item.querySelector('[data-row-incoming]').textContent = row.incoming || '';
                if (row.status === 'too_long') {
                    var note = item.querySelector('[data-row-note]');
                    note.textContent = L.tooLong;
                    show(note, true);
                }
                listEl.appendChild(item);
            });
            summaryEl.textContent = actionable.length
                ? fill(L.importSummary, { n: actionable.length })
                : L.importNoChange;
            show(listEl, actionable.length > 0);
            show(applyBtn, actionable.some(function (row) { return row.status !== 'too_long'; }));
            warningsEl.textContent = '';
            (data.warnings || []).forEach(function (text) {
                var line = document.createElement('p');
                line.textContent = text;
                warningsEl.appendChild(line);
            });
            show(warningsEl, (data.warnings || []).length > 0);
            var ignored = (data.ignored || []).map(function (row) {
                return row.heading;
            });
            ignoredEl.textContent = ignored.length ? fill(L.importIgnored, { list: ignored.join(', ') }) : '';
            show(ignoredEl, ignored.length > 0);
            step('review');
        }

        function read() {
            var file = fileInput && fileInput.files && fileInput.files[0];
            show(errorEl, false);
            if (!file) {
                fail(L.importNeedsFile);
                return;
            }
            var data = new FormData();
            data.append('document', file);
            analyze.disabled = true;
            http(cfg.importUrl, { method: 'POST', body: data, headers: { Accept: 'application/json' } })
                .then(readJson)
                .then(function (reply) {
                    analyze.disabled = false;
                    if (!reply.ok || !reply.body.ok) {
                        fail(reply.body.error || L.importFailed);
                        return;
                    }
                    review(reply.body);
                })
                .catch(function () {
                    analyze.disabled = false;
                    fail(L.importFailed);
                });
        }

        function apply() {
            var picked = {};
            var count = 0;
            listEl.querySelectorAll('[data-row-check]').forEach(function (check) {
                var key = check.getAttribute('data-key');
                var row = (result.chapters || []).filter(function (item) {
                    return item.key === key;
                })[0];
                if (check.checked && !check.disabled && row) {
                    picked[key] = row.html || '';
                    count += 1;
                }
            });
            if (!count) {
                summaryEl.textContent = L.importNothing;
                return;
            }
            applyBtn.disabled = true;
            before = {};
            Object.keys(picked).forEach(function (key) {
                before[key] = { html: chapters[key].html, edited: chapters[key].edited };
                window.clearTimeout(chapters[key].timer);
            });
            postJson(cfg.saveUrl, { sections: picked })
                .then(function (reply) {
                    applyBtn.disabled = false;
                    var saved = (reply.body && reply.body.saved) || {};
                    var keys = Object.keys(saved);
                    keys.forEach(function (key) {
                        var st = chapters[key];
                        st.savedHtml = saved[key].html || '';
                        applyText(st, st.savedHtml, true);
                        hideUndo(st);
                    });
                    Object.keys(before).forEach(function (key) {
                        if (!saved[key]) {
                            delete before[key];
                        }
                    });
                    var failed = (reply.body && reply.body.failed) || {};
                    var message = keys.length === 1 ? L.importAppliedOne : fill(L.importApplied, { n: keys.length });
                    var problems = Object.keys(failed).map(function (key) {
                        return (chapters[key] ? chapters[key].label + ': ' : '') + failed[key];
                    });
                    if (!keys.length && reply.body && reply.body.error) {
                        problems.push(reply.body.error);
                    }
                    doneEl.textContent = [message].concat(problems).join(' ');
                    show(undoBtn, keys.length > 0);
                    step('done');
                })
                .catch(function () {
                    applyBtn.disabled = false;
                    summaryEl.textContent = L.importFailed;
                });
        }

        function undo() {
            var restore = {};
            Object.keys(before).forEach(function (key) {
                restore[key] = before[key].html;
            });
            if (!Object.keys(restore).length) {
                return;
            }
            undoBtn.disabled = true;
            postJson(cfg.saveUrl, { sections: restore })
                .then(function (reply) {
                    undoBtn.disabled = false;
                    var saved = (reply.body && reply.body.saved) || {};
                    Object.keys(saved).forEach(function (key) {
                        var st = chapters[key];
                        st.savedHtml = saved[key].html || '';
                        applyText(st, st.savedHtml, before[key].edited);
                    });
                    before = {};
                    doneEl.textContent = L.importUndone;
                    show(undoBtn, false);
                })
                .catch(function () {
                    undoBtn.disabled = false;
                });
        }

        document.querySelectorAll('[data-act="import-open"]').forEach(function (button) {
            button.addEventListener('click', function () {
                var menu = document.getElementById('dref-export-menu');
                if (menu) {
                    menu.classList.add('hidden');
                }
                open();
            });
        });
        if (analyze) {
            analyze.addEventListener('click', read);
        }
        if (applyBtn) {
            applyBtn.addEventListener('click', apply);
        }
        if (undoBtn) {
            undoBtn.addEventListener('click', undo);
        }
        var back = modal.querySelector('[data-import-back]');
        if (back) {
            back.addEventListener('click', function () {
                step('pick');
            });
        }
        step('pick');
    }

    // ---- start --------------------------------------------------------------

    function start() {
        order.forEach(function (key) {
            refresh(chapters[key]);
        });
        initImport();
        initPanel(visiblePanel());
        document.querySelectorAll('#dref-draft-tabs [data-tab]').forEach(function (tab) {
            tab.addEventListener('click', function () {
                window.setTimeout(function () {
                    initPanel(visiblePanel());
                }, 60);
            });
        });
        (cfg.sectionJobs || []).forEach(function (payload) {
            var st = chapters[payload.section];
            if (!st || isTerminal(payload.status)) {
                return;
            }
            setGenerating(st, true, payload.message || L.badge);
            follow(st, payload, { html: st.html, edited: st.edited, sources: copySources(st.sources) });
        });
    }

    if (document.readyState === 'complete') {
        start();
    } else {
        window.addEventListener('load', start);
    }
})();
