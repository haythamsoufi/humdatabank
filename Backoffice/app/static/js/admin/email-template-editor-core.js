/**
 * Shared HTML / Visual (TinyMCE) email template editor used by Communication Center compose.
 * Mirrors the Settings email template editor behaviour (syntax highlight, head/body split, var preview).
 */
(function (global) {
    'use strict';

    const HTE_JINJA_CLS = 'htd-email-jinja';
    const HTE_JINJA_OPEN = '{' + '{';
    const HTE_JINJA_RE = new RegExp('\\{\\{[\\s\\S]*?\\}\\}', 'g');
    const ETM_CLASS_EDIT = 'email-template-mode-btn email-template-mode-edit-btn inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium min-w-[4.75rem] border-0 transition-colors';
    const ETM_CLASS_VISUAL = 'email-template-mode-btn email-template-mode-visual-btn inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium min-w-[4.75rem] border-0 transition-colors';

    let tinymceLoadPromise = null;

    function escCssSelector(s) {
        if (global.escapeCssSelector) return global.escapeCssSelector(s);
        return String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }

    function escapeHtmlText(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function highlightJinjaMustacheToHtml(raw) {
        if (!raw) return '';
        const open = '{{';
        const close = '}}';
        const out = [];
        let last = 0;
        let i = 0;
        while (i < raw.length) {
            const start = raw.indexOf(open, i);
            if (start === -1) break;
            if (start > last) out.push(escapeHtmlText(raw.slice(last, start)));
            const end = raw.indexOf(close, start + 2);
            if (end === -1) break;
            out.push('<span class="email-template-jinja-var">');
            out.push(escapeHtmlText(raw.slice(start, end + 2)));
            out.push('</span>');
            last = end + 2;
            i = end + 2;
        }
        out.push(escapeHtmlText(raw.slice(last)));
        return out.join('');
    }

    function updateSyntaxHighlight(ta) {
        if (!ta) return;
        const wrap = ta.closest('.email-template-edit-wrap');
        const pre = wrap ? wrap.querySelector('.email-template-syntax-backdrop') : null;
        if (!pre) return;
        pre.innerHTML = highlightJinjaMustacheToHtml(ta.value);
        pre.style.height = ta.scrollHeight + 'px';
        pre.style.minHeight = ta.clientHeight + 'px';
        pre.style.transform = 'translateY(' + (-ta.scrollTop) + 'px)';
    }

    function bindSyntaxToTextarea(ta) {
        if (!ta || ta.dataset.syntaxBound === '1') return;
        ta.dataset.syntaxBound = '1';
        ta.addEventListener('input', () => updateSyntaxHighlight(ta));
        ta.addEventListener('scroll', () => {
            const wrap = ta.closest('.email-template-edit-wrap');
            const pre = wrap ? wrap.querySelector('.email-template-syntax-backdrop') : null;
            if (pre) pre.style.transform = 'translateY(' + (-ta.scrollTop) + 'px)';
        });
        if (global.ResizeObserver) {
            (new global.ResizeObserver(() => updateSyntaxHighlight(ta))).observe(ta);
        }
        updateSyntaxHighlight(ta);
    }

    function base64EncodeUtf8(str) {
        try {
            return btoa(unescape(encodeURIComponent(String(str || ''))));
        } catch (_) {
            return '';
        }
    }

    function wrapPreviewBody(innerObj) {
        try {
            const payloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(innerObj))));
            return JSON.stringify({ payload: payloadB64 });
        } catch (_) {
            return JSON.stringify(innerObj);
        }
    }

    function getCsrfToken() {
        const m = document.querySelector('meta[name="csrf-token"]');
        if (m && m.getAttribute('content')) return m.getAttribute('content');
        const inp = document.querySelector('input[name="csrf_token"]');
        return inp ? inp.value || '' : '';
    }

    function isRtlLang(code) {
        if (!code || typeof code !== 'string') return false;
        const base = String(code).trim().toLowerCase().split('_')[0].split('-')[0];
        return ['ar', 'he', 'iw', 'fa', 'ur', 'ps', 'dv', 'ckb', 'sd', 'ug'].includes(base);
    }

    function isFullHtmlDocumentFragment(s) {
        if (!s || typeof s !== 'string') return false;
        const t = s.trim();
        return t.indexOf('<!DOCTYPE') === 0 || /^<html[\s>]/i.test(t);
    }

    function shouldSkipJinjaWalkEl(el) {
        if (!el || el.nodeType !== 1) return false;
        const tag = (el.nodeName || '').toLowerCase();
        if (tag === 'script' || tag === 'style' || tag === 'noscript' || tag === 'textarea') return true;
        if (el.classList && el.classList.contains(HTE_JINJA_CLS)) return true;
        return false;
    }

    function jinjaTextNodeHasPlaceholder(t) {
        if (!t || t.indexOf(HTE_JINJA_OPEN) < 0) return false;
        HTE_JINJA_RE.lastIndex = 0;
        return HTE_JINJA_RE.test(t);
    }

    function processJinjaInTextNode(textNode, doc) {
        if (!textNode || textNode.nodeType !== 3) return;
        const t = textNode.nodeValue;
        if (!jinjaTextNodeHasPlaceholder(t)) return;
        HTE_JINJA_RE.lastIndex = 0;
        const parent = textNode.parentNode;
        if (!parent) return;
        let m;
        let last = 0;
        const fr = doc.createDocumentFragment();
        HTE_JINJA_RE.lastIndex = 0;
        while ((m = HTE_JINJA_RE.exec(t)) !== null) {
            if (m.index > last) fr.appendChild(doc.createTextNode(t.slice(last, m.index)));
            const sp = doc.createElement('span');
            sp.setAttribute('class', HTE_JINJA_CLS);
            sp.setAttribute('data-htd-jinja', '1');
            sp.appendChild(doc.createTextNode(m[0]));
            fr.appendChild(sp);
            last = m.index + m[0].length;
        }
        if (last < t.length) fr.appendChild(doc.createTextNode(t.slice(last)));
        if (fr.childNodes.length) {
            try { parent.replaceChild(fr, textNode); } catch (_) { /* ignore */ }
        }
    }

    function walkJinjaInNode(root, doc) {
        if (!root) return;
        let n = root.firstChild;
        while (n) {
            const next = n.nextSibling;
            if (n.nodeType === 1) {
                if (!shouldSkipJinjaWalkEl(n)) walkJinjaInNode(n, doc);
            } else if (n.nodeType === 3) {
                processJinjaInTextNode(n, doc);
            }
            n = next;
        }
    }

    function applyJinjaHighlightToBodyHtmlString(bodyHtml) {
        if (bodyHtml == null || !String(bodyHtml) || String(bodyHtml).indexOf(HTE_JINJA_OPEN) < 0) {
            return String(bodyHtml || '');
        }
        try {
            const d = new global.DOMParser().parseFromString(
                '<!DOCTYPE html><html><body id="__htd_ja"><div id="__htd_jw">' + String(bodyHtml) + '</div></body></html>',
                'text/html'
            );
            const wrap = d.getElementById('__htd_jw');
            if (!wrap) return String(bodyHtml);
            walkJinjaInNode(wrap, d);
            return wrap.innerHTML;
        } catch (_) {
            return String(bodyHtml);
        }
    }

    function stripJinjaHighlightFromBodyHtmlString(bodyHtml) {
        const s = String(bodyHtml || '');
        if (s.indexOf(HTE_JINJA_CLS) < 0 && s.indexOf('data-htd-jinja') < 0) return s;
        try {
            const d = new global.DOMParser().parseFromString(
                '<!DOCTYPE html><html><body><div id="__htd_jw2">' + s + '</div></body></html>',
                'text/html'
            );
            const wrap = d.getElementById('__htd_jw2');
            if (!wrap) return s;
            wrap.querySelectorAll('span.' + HTE_JINJA_CLS + ',span[data-htd-jinja]').forEach((sp) => {
                const p = sp.parentNode;
                if (!p) return;
                while (sp.firstChild) p.insertBefore(sp.firstChild, sp);
                p.removeChild(sp);
            });
            return wrap.innerHTML;
        } catch (_) {
            return s;
        }
    }

    function mergePreviewWithSourceHead(placeholderSource, serverHtml) {
        if (!serverHtml || typeof serverHtml !== 'string') return serverHtml || '';
        const ph = (placeholderSource || '').trim();
        if (!ph) return serverHtml;
        if (!/<style[\s>]/i.test(ph) && !/<link[^>]+rel\s*=\s*["']?stylesheet/i.test(ph)) {
            return serverHtml;
        }
        try {
            const parser = new global.DOMParser();
            const dPh = parser.parseFromString(ph, 'text/html');
            const dSv = parser.parseFromString(serverHtml, 'text/html');
            const headInner = (dPh.head && dPh.head.innerHTML) ? dPh.head.innerHTML.trim() : '';
            if (!headInner) return serverHtml;
            const bodyInner = (dSv.body && dSv.body.innerHTML) ? dSv.body.innerHTML : serverHtml;
            return '<!DOCTYPE html>\n<html><head>' + headInner + '</head><body>' + bodyInner + '</body></html>';
        } catch (_) {
            return serverHtml;
        }
    }

    function applyRtlToPreviewHtml(html, langCode) {
        if (!isRtlLang(langCode)) return html;
        if (!html || typeof html !== 'string') return html;
        if (/<html[^>]*\bdir\s*=/i.test(html)) return html;
        const trimmed = html.trim();
        if (/^<!DOCTYPE/i.test(trimmed) || /^<html/i.test(trimmed)) {
            return html.replace(/<html(\s[^>]*)?>/i, (full, inner) => {
                if (inner && /\bdir\s*=/.test(inner)) return full;
                return '<html' + (inner || '') + ' dir="rtl">';
            });
        }
        return '<div dir="rtl" style="direction:rtl;text-align:start;">' + html + '</div>';
    }

    function loadTinymceIfNeeded(tinymceBaseUrl, done) {
        if (global.tinymce) {
            setTimeout(done, 0);
            return;
        }
        if (tinymceLoadPromise) {
            tinymceLoadPromise.then(() => done());
            return;
        }
        tinymceLoadPromise = new Promise((resolve) => {
            const s = document.createElement('script');
            s.src = tinymceBaseUrl + '/tinymce.min.js';
            s.onload = () => resolve(1);
            s.onerror = () => resolve(0);
            document.head.appendChild(s);
        });
        tinymceLoadPromise.then(() => done());
    }

    function createEditor(options) {
        const editorKey = options.editorKey;
        const rootEl = options.rootEl || document;
        const tinymceBaseUrl = options.tinymceBaseUrl || '';
        const previewUrl = options.previewUrl || '';
        const labels = options.labels || {};
        const getApiTemplateKey = options.getApiTemplateKey || (() => editorKey);
        const getPreviewExtraFields = options.getPreviewExtraFields || (() => ({}));
        const onDirty = options.onDirty || (() => {});

        const state = {
            viewMode: 'edit',
            varMode: 'placeholders',
            headInner: '',
            varToggleApi: null,
        };

        const mainTa = document.getElementById(editorKey);
        const visTa = document.getElementById(editorKey + '-visual');
        const editPane = rootEl.querySelector('.email-template-edit-pane');
        const visPane = rootEl.querySelector('.email-template-visual-pane');
        const surface = rootEl.querySelector('.email-template-code-surface');

        function getTinymce() {
            if (!global.tinymce) return null;
            return global.tinymce.get(editorKey + '-visual') || null;
        }

        function markDirty() {
            onDirty();
        }

        function injectHeadIntoTinymceEd(ed) {
            if (!ed || !ed.getDoc) return;
            const doc = ed.getDoc();
            if (!doc || !doc.head) return;
            doc.head.querySelectorAll('[data-email-template-head="1"]').forEach((n) => {
                try { n.remove(); } catch (_) { /* ignore */ }
            });
            const headInner = state.headInner;
            if (!headInner || !String(headInner).trim()) return;
            try {
                const container = new global.DOMParser().parseFromString(
                    '<!DOCTYPE html><html><head>' + String(headInner) + '</head><body></body></html>',
                    'text/html'
                );
                if (!container || !container.head) return;
                container.head.children.forEach((el) => {
                    if (!el || el.nodeName === '#text') return;
                    const tag = (el.nodeName || '').toUpperCase();
                    if (tag !== 'TITLE' && tag !== 'STYLE' && tag !== 'LINK' && tag !== 'META') return;
                    try {
                        const imp = doc.importNode(el, true);
                        imp.setAttribute('data-email-template-head', '1');
                        doc.head.appendChild(imp);
                    } catch (_) { /* ignore */ }
                });
            } catch (_) { /* ignore */ }
        }

        function injectJinjaVarHighlightStyleInTinymceEd(ed) {
            if (!ed || !ed.getDoc) return;
            const doc = ed.getDoc();
            if (!doc || !doc.head) return;
            doc.head.querySelectorAll('style[data-email-jinja-hl]').forEach((n) => {
                try { n.remove(); } catch (_) { /* ignore */ }
            });
            const st = doc.createElement('style');
            st.setAttribute('data-email-jinja-hl', '2');
            st.textContent =
                '.' + HTE_JINJA_CLS + '{' +
                'box-sizing:border-box;color:#0f3d3a;background:#fff;border:1.5px solid #115e59;' +
                'box-shadow:0 0 0 1px rgba(255,255,255,0.9),0 1px 3px rgba(0,0,0,0.2);' +
                'border-radius:4px;padding:0.08em 0.24em;font-weight:600;' +
                'font-family:ui-monospace,Consolas,Monaco,Menlo,monospace;font-size:0.9em;letter-spacing:0.02em}';
            try { doc.head.appendChild(st); } catch (_) { /* ignore */ }
        }

        function afterTinymceBodySet(ed) {
            if (!ed) return;
            global.setTimeout(() => {
                injectHeadIntoTinymceEd(ed);
                injectJinjaVarHighlightStyleInTinymceEd(ed);
            }, 0);
        }

        function normalizeBodyForDisplay(bodyStr) {
            let s0 = String(bodyStr || '');
            s0 = stripJinjaHighlightFromBodyHtmlString(s0);
            if (state.varMode === 'values') return s0;
            return applyJinjaHighlightToBodyHtmlString(s0);
        }

        function setTinymceContent(ed, html) {
            if (!ed) return;
            if (html == null || !String(html).trim()) {
                state.headInner = '';
                ed.setContent('');
                return;
            }
            const h = String(html);
            try {
                const d = new global.DOMParser().parseFromString(h, 'text/html');
                const headInner = (d.head && d.head.innerHTML) ? d.head.innerHTML.trim() : '';
                const bodyEl = d.body;
                if (!bodyEl || (!headInner && !isFullHtmlDocumentFragment(h) && h.indexOf('<head') < 0)) {
                    state.headInner = '';
                    ed.setContent(normalizeBodyForDisplay(h), { format: 'html' });
                    afterTinymceBodySet(ed);
                    return;
                }
                state.headInner = headInner;
                ed.setContent(normalizeBodyForDisplay(bodyEl.innerHTML), { format: 'html' });
                afterTinymceBodySet(ed);
            } catch (_) {
                state.headInner = '';
                ed.setContent(normalizeBodyForDisplay(h), { format: 'html' });
                afterTinymceBodySet(ed);
            }
        }

        function rebuildFromTinymce() {
            const m = getTinymce();
            if (!m) return mainTa ? mainTa.value : '';
            const bodyInner = stripJinjaHighlightFromBodyHtmlString(m.getContent() || '');
            const headInner = state.headInner || '';
            if (!String(headInner).trim()) return bodyInner;
            return '<!DOCTYPE html>\n<html><head>' + headInner + '</head><body>' + bodyInner + '</body></html>';
        }

        function syncVisualToTextarea() {
            if (state.varMode === 'values') return;
            const m = getTinymce();
            if (!m || !mainTa) return;
            mainTa.value = rebuildFromTinymce();
            updateSyntaxHighlight(mainTa);
        }

        function destroyTinymce() {
            const m = getTinymce();
            if (m) m.remove();
            state.varMode = 'placeholders';
            state.varToggleApi = null;
            state.headInner = '';
        }

        function updateModeToggleUi() {
            const isEdit = state.viewMode === 'edit';
            rootEl.querySelectorAll('.email-template-mode-edit-btn').forEach((btn) => {
                btn.className = ETM_CLASS_EDIT + (isEdit
                    ? ' bg-white text-blue-600 relative z-10'
                    : ' bg-gray-50 text-gray-500 hover:text-gray-700 hover:bg-gray-100');
                btn.setAttribute('aria-pressed', isEdit ? 'true' : 'false');
            });
            rootEl.querySelectorAll('.email-template-mode-visual-btn').forEach((btn) => {
                btn.className = ETM_CLASS_VISUAL + (isEdit
                    ? ' bg-gray-50 text-gray-500 hover:text-gray-700 hover:bg-gray-100'
                    : ' bg-white text-blue-600 relative z-10');
                btn.setAttribute('aria-pressed', isEdit ? 'false' : 'true');
            });
        }

        function buildTinymceOptions() {
            const lang = (mainTa && mainTa.dataset && mainTa.dataset.currentLang) ? String(mainTa.dataset.currentLang) : 'en';
            const rtl = isRtlLang(lang);
            return {
                selector: '#' + escCssSelector(editorKey) + '-visual',
                height: 480,
                resize: false,
                statusbar: false,
                toolbar_mode: 'wrap',
                menubar: false,
                branding: false,
                promotion: false,
                plugins: 'image link lists table visualblocks',
                toolbar: 'undo redo | blocks | bold italic underline | forecolor backcolor | alignleft aligncenter alignright | bullist numlist outdent indent | link image table | emailvarmode | removeformat',
                table_toolbar: 'tableprops tabledelete | tablecellprops tablerowprops | tablemergecells tablesplitcells | tablecellvalign | tableinsertrowbefore tableinsertrowafter tabledeleterow | tableinsertcolbefore tableinsertcolafter tabledeletecol | tablecellbackgroundcolor | tablecellborderwidth tablecellborderstyle',
                valid_elements: '*[*]',
                invalid_elements: '',
                verify_html: false,
                entity_encoding: 'raw',
                apply_source_formatting: false,
                remove_trailing_brs: false,
                convert_urls: false,
                relative_urls: false,
                remove_script_host: false,
                base_url: tinymceBaseUrl,
                suffix: '.min',
                skin: 'oxide',
                content_css: false,
                directionality: rtl ? 'rtl' : 'ltr',
                setup(ed) {
                    ed.on('input change keyup', markDirty);
                    if (ed.ui && ed.ui.registry) {
                        ed.ui.registry.addToggleButton('emailvarmode', {
                            text: labels.variables || 'Var',
                            icon: 'preview',
                            tooltip: labels.tinymceVarTip || '',
                            onAction(api) {
                                if (state.varMode === 'values') {
                                    const ph = mainTa ? mainTa.value : '';
                                    state.varMode = 'placeholders';
                                    setTinymceContent(ed, ph);
                                    if (api) api.setActive(false);
                                    return;
                                }
                                if (api) api.setActive(false);
                                syncVisualToTextarea();
                                if (api) api.setEnabled(false);
                                runSampleValuesRequest((err, outHtml) => {
                                    if (api) api.setEnabled(true);
                                    if (err) {
                                        const msg = err.message === 'empty'
                                            ? (labels.addContentFirst || 'Add content first.')
                                            : (err.message || labels.couldNotLoadSampleValues || 'Preview failed.');
                                        if (global.showAlert) global.showAlert(msg, 'warning');
                                        else if (global.showToast) global.showToast(msg, 'warning');
                                        if (api) api.setActive(false);
                                        return;
                                    }
                                    state.varMode = 'values';
                                    setTinymceContent(ed, outHtml);
                                    if (api) api.setActive(true);
                                });
                            },
                            onSetup(api) {
                                state.varToggleApi = api;
                                try { api.setActive(false); } catch (_) { /* ignore */ }
                                return () => {
                                    if (state.varToggleApi === api) state.varToggleApi = null;
                                };
                            },
                        });
                    }
                },
            };
        }

        function startTinymce() {
            if (!visTa || getTinymce()) return;
            loadTinymceIfNeeded(tinymceBaseUrl, () => {
                if (!global.tinymce || getTinymce()) return;
                try {
                    global.tinymce.init(Object.assign({
                        init_instance_callback(ed) {
                            const b = ed.getBody();
                            if (b) b.setAttribute('spellcheck', 'true');
                            const html = mainTa ? mainTa.value : (visTa.value || '');
                            if (html) setTinymceContent(ed, html);
                        },
                    }, buildTinymceOptions()));
                } catch (e) {
                    if (global.console && console.warn) console.warn('TinyMCE init', e);
                }
            });
        }

        function loadVisualPane() {
            state.varMode = 'placeholders';
            if (state.varToggleApi) {
                try { state.varToggleApi.setActive(false); } catch (_) { /* ignore */ }
            }
            const html = mainTa ? mainTa.value : '';
            if (visTa) visTa.value = html;
            const existing = getTinymce();
            if (existing) {
                setTinymceContent(existing, html);
                return;
            }
            startTinymce();
        }

        function applyViewMode() {
            if (!editPane || !visPane) return;
            if (state.viewMode === 'edit') {
                syncVisualToTextarea();
                destroyTinymce();
                editPane.classList.remove('hidden');
                visPane.classList.add('hidden');
                if (mainTa) global.setTimeout(() => updateSyntaxHighlight(mainTa), 0);
            } else {
                editPane.classList.add('hidden');
                visPane.classList.remove('hidden');
                loadVisualPane();
            }
            updateModeToggleUi();
        }

        function runSampleValuesRequest(onDone) {
            if (!previewUrl) {
                onDone(new Error('url'));
                return;
            }
            if (!mainTa) {
                onDone(new Error('no ta'));
                return;
            }
            syncVisualToTextarea();
            const plang = (mainTa.dataset && mainTa.dataset.currentLang) ? String(mainTa.dataset.currentLang).trim() : 'en';
            const src = mainTa.value || '';
            const trimmed = src.trim();
            if (!trimmed) {
                onDone(new Error('empty'));
                return;
            }
            const b64 = base64EncodeUtf8(trimmed);
            if (!b64) {
                onDone(new Error('b64'));
                return;
            }
            const body = wrapPreviewBody(Object.assign({
                template_key: getApiTemplateKey(),
                html_b64: b64,
                template_language: plang,
            }, getPreviewExtraFields()));
            const fn = (global.getApiFetch && global.getApiFetch()) || global.apiFetch || global.fetch;
            fn(previewUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body,
            }).then((resp) => {
                if (typeof resp.json !== 'function') {
                    onDone(new Error(labels.couldNotLoadSampleValues || 'Preview failed.'));
                    return;
                }
                return window.responseAsResult(resp);
            }).then((result) => {
                if (!result) return;
                const p = result.payload || {};
                if (result.ok && p.success && typeof p.html === 'string' && p.html.trim()) {
                    const merged = mergePreviewWithSourceHead(src, p.html);
                    onDone(null, applyRtlToPreviewHtml(merged, plang));
                    return;
                }
                onDone(new Error(p.error || p.message || labels.couldNotLoadSampleValues || 'Preview failed.'));
            }).catch((err) => onDone(err));
        }

        function insertVariable(variable) {
            const v = String(variable || '');
            if (state.viewMode === 'visual' && getTinymce()) {
                if (state.varMode === 'values') {
                    state.varMode = 'placeholders';
                    setTinymceContent(getTinymce(), mainTa ? mainTa.value : '');
                    if (state.varToggleApi) {
                        try { state.varToggleApi.setActive(false); } catch (_) { /* ignore */ }
                    }
                }
                const ed = getTinymce();
                if (ed) {
                    ed.insertContent(v, { format: 'raw' });
                    ed.focus();
                    markDirty();
                    return;
                }
                setViewMode('edit');
            }
            if (!mainTa) return;
            const start = mainTa.selectionStart;
            const end = mainTa.selectionEnd;
            const text = mainTa.value;
            mainTa.value = text.substring(0, start) + v + text.substring(end);
            mainTa.focus();
            mainTa.setSelectionRange(start + v.length, start + v.length);
            markDirty();
            updateSyntaxHighlight(mainTa);
        }

        function setViewMode(mode) {
            if (mode !== 'edit' && mode !== 'visual') return;
            state.viewMode = mode;
            applyViewMode();
        }

        function getHtml() {
            if (state.viewMode === 'visual') syncVisualToTextarea();
            return mainTa ? (mainTa.value || '').trim() : '';
        }

        function setHtml(html) {
            if (!mainTa) return;
            mainTa.value = html == null ? '' : String(html);
            markDirty();
            updateSyntaxHighlight(mainTa);
            if (state.viewMode === 'visual') {
                const m = getTinymce();
                if (m) setTinymceContent(m, mainTa.value);
                else if (visTa) visTa.value = mainTa.value;
            }
        }

        function bindEvents() {
            if (mainTa) bindSyntaxToTextarea(mainTa);

            rootEl.querySelectorAll('.email-template-mode-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const mode = btn.getAttribute('data-mode');
                    if (mode === 'edit') setViewMode('edit');
                    else if (mode === 'visual') setViewMode('visual');
                });
            });

            rootEl.querySelectorAll('.insert-variable-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    insertVariable(btn.getAttribute('data-variable') || '');
                });
            });

            if (surface) {
                surface.setAttribute('data-template-key', editorKey);
            }
        }

        bindEvents();
        updateModeToggleUi();

        return {
            getHtml,
            setHtml,
            setViewMode,
            getViewMode: () => state.viewMode,
            syncVisualToTextarea,
            destroy: () => {
                syncVisualToTextarea();
                destroyTinymce();
            },
            insertVariable,
        };
    }

    global.EmailTemplateEditorCore = {
        createEditor,
        updateSyntaxHighlight,
        bindSyntaxToTextarea,
    };
})(window);
