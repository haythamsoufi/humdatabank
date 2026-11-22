(function () {
    'use strict';
    var exportRoot = document.getElementById('dref-export');
    var exportButton = document.getElementById('dref-export-btn');
    var exportMenu = document.getElementById('dref-export-menu');
    if (exportRoot && exportButton && exportMenu) {
        function closeExport() {
            exportMenu.classList.add('hidden');
            exportButton.setAttribute('aria-expanded', 'false');
        }

        exportButton.addEventListener('click', function (event) {
            event.stopPropagation();
            var open = exportMenu.classList.contains('hidden');
            exportMenu.classList.toggle('hidden', !open);
            exportButton.setAttribute('aria-expanded', open ? 'true' : 'false');
        });

        document.addEventListener('click', function (event) {
            if (!exportRoot.contains(event.target)) closeExport();
        });

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') closeExport();
        });
    }

    var sourcesModal = document.getElementById('dref-sources-modal');
    var sourcesConfigEl = document.getElementById('dref-sources-config');
    if (sourcesModal && sourcesConfigEl) {
        var sourcesConfig = {};
        try {
            sourcesConfig = JSON.parse(sourcesConfigEl.textContent || '{}');
        } catch (error) {
            sourcesConfig = {};
        }
        if (sourcesModal.parentElement !== document.body) {
            document.body.appendChild(sourcesModal);
        }
        var sourcesController = window.ModalUtils
            ? window.ModalUtils.makeModal(sourcesModal, { closeSelector: '.close-modal' })
            : null;
        var sourcesRows = Array.isArray(sourcesConfig.sources) ? sourcesConfig.sources.slice() : [];
        var sourcesTouched = false;
        var sourcesFocus = '';
        var sourcesList = sourcesModal.querySelector('[data-sources-list]');
        var sourcesIntro = sourcesModal.querySelector('[data-sources-intro]');
        var sourcesUnrecorded = sourcesModal.querySelector('[data-sources-unrecorded]');
        var sourcesNone = sourcesModal.querySelector('[data-sources-none]');
        var sourcesTitle = document.getElementById('dref-sources-modal-title');
        if (sourcesTitle && !sourcesTitle.getAttribute('data-sources-title')) {
            sourcesTitle.setAttribute('data-sources-title', sourcesTitle.textContent || '');
        }
        var usedForLabel = sourcesList ? sourcesList.getAttribute('data-used-for') || '' : '';

        var sourceMonths = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

        function sourceDate(value) {
            var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || '');
            if (!match) {
                return value || '';
            }
            return Number(match[3]) + ' ' + sourceMonths[Number(match[2]) - 1] + ' ' + match[1];
        }

        function sourceHref(url) {
            if (typeof url !== 'string') {
                return '';
            }
            if (/^\/api\/ai\/documents\/\d+\/download$/.test(url)) {
                return url;
            }
            if (/^\/dref-monitoring\/operations\/\d+(?:\/drafts\/\d+)?(?:\?tab=reporting)?$/.test(url)) {
                return url;
            }
            if (/^\/assignment\/\d+$/.test(url)) {
                return url;
            }
            if (/^https?:\/\/[^\s"'<>\\]+$/.test(url)) {
                return url;
            }
            return '';
        }

        function renderSources() {
            if (!sourcesList) {
                return;
            }
            sourcesList.textContent = '';
            var byChapter = {};
            sourcesRows.forEach(function (row) {
                var key = row && row.chapter ? String(row.chapter) : '';
                if (!key) {
                    return;
                }
                if (!byChapter[key]) {
                    byChapter[key] = [];
                }
                byChapter[key].push(row);
            });
            var chapters = Array.isArray(sourcesConfig.chapters) ? sourcesConfig.chapters : [];
            var kinds = sourcesConfig.kinds || {};
            var chapter = null;
            chapters.forEach(function (item) {
                if (item.key === sourcesFocus) {
                    chapter = item;
                }
            });
            if (sourcesTitle) {
                sourcesTitle.textContent = chapter && chapter.label ? chapter.label : sourcesTitle.getAttribute('data-sources-title') || sourcesTitle.textContent;
            }
            var rows = byChapter[sourcesFocus] || [];
            if (rows.length) {
                var block = document.createElement('section');
                block.className = 'dref-sources__chapter';
                rows.forEach(function (row) {
                    var item = document.createElement('article');
                    item.className = 'dref-sources__item';
                    var href = sourceHref(row.url);
                    var title = document.createElement(href ? 'a' : 'p');
                    title.className = 'dref-sources__title';
                    title.textContent = row.title || row.id || '';
                    if (href) {
                        title.setAttribute('href', href);
                        title.setAttribute('target', '_blank');
                        title.setAttribute('rel', 'noopener noreferrer');
                    }
                    item.appendChild(title);
                    var metaBits = [kinds[row.kind] || '', sourceDate(row.date)].filter(Boolean);
                    if (metaBits.length) {
                        var meta = document.createElement('p');
                        meta.className = 'dref-sources__meta';
                        meta.textContent = metaBits.join(' · ');
                        item.appendChild(meta);
                    }
                    if (row.locator) {
                        var locator = document.createElement('p');
                        locator.className = 'dref-sources__locator';
                        locator.textContent = row.locator;
                        item.appendChild(locator);
                    }
                    if (row.used_for) {
                        var fact = document.createElement('p');
                        fact.className = 'dref-sources__fact';
                        fact.textContent = usedForLabel ? usedForLabel + ': ' + row.used_for : row.used_for;
                        item.appendChild(fact);
                    }
                    block.appendChild(item);
                });
                sourcesList.appendChild(block);
            }
            var hasRows = sourcesList.childElementCount > 0;
            sourcesList.classList.toggle('hidden', !hasRows);
            var state = 'none';
            if (hasRows) {
                state = 'listed';
            } else if (!sourcesTouched && sourcesConfig.state === 'unrecorded') {
                state = 'unrecorded';
            }
            if (sourcesIntro) {
                sourcesIntro.classList.toggle('hidden', state !== 'listed');
            }
            if (sourcesUnrecorded) {
                sourcesUnrecorded.classList.toggle('hidden', state !== 'unrecorded');
            }
            if (sourcesNone) {
                sourcesNone.classList.toggle('hidden', state !== 'none');
            }
        }

        function openSources(chapter) {
            sourcesFocus = chapter || '';
            renderSources();
            if (sourcesController) {
                sourcesController.openModal();
            } else {
                sourcesModal.classList.remove('hidden');
            }
            if (sourcesFocus) {
                var target = sourcesModal.querySelector('[data-sources-chapter="' + sourcesFocus + '"]');
                if (target && target.scrollIntoView) {
                    target.scrollIntoView({ block: 'start' });
                }
            }
        }

        document.addEventListener('click', function (event) {
            var button = event.target.closest ? event.target.closest('[data-act="sources"]') : null;
            if (!button) {
                return;
            }
            var key = button.getAttribute('data-sources-for');
            if (!key) {
                var host = button.closest('[data-chapter]');
                key = host ? host.getAttribute('data-chapter') : '';
            }
            if (key) {
                openSources(key);
            }
        });
        renderSources();
        window.DrefSources = {
            list: function () {
                return sourcesRows.slice();
            },
            set: function (rows) {
                sourcesRows = Array.isArray(rows) ? rows.slice() : [];
                sourcesTouched = true;
                renderSources();
            }
        };
    }

    var article = document.querySelector('.dref-report');
    var narrativePanel = document.getElementById('panel-narrative');
    var emptyToggle = document.querySelector('input[data-show-empty]');
    var EMPTY_KEY = 'dref-show-empty';

    function exportLinks(includeEmpty) {
        document.querySelectorAll('[data-dref-export]').forEach(function (link) {
            var url = new URL(link.getAttribute('href'), window.location.origin);
            if (includeEmpty) {
                url.searchParams.set('include_empty', '1');
            } else {
                url.searchParams.delete('include_empty');
            }
            link.setAttribute('href', url.pathname + url.search);
        });
    }

    function showEmpty(on) {
        if (article) {
            article.setAttribute('data-show-empty', on ? '1' : '0');
        }
        if (narrativePanel) {
            narrativePanel.setAttribute('data-show-empty', on ? '1' : '0');
        }
        exportLinks(on);
    }

    if (emptyToggle) {
        var stored = false;
        try {
            stored = window.sessionStorage.getItem(EMPTY_KEY) === '1';
        } catch (error) {
            stored = false;
        }
        emptyToggle.checked = stored;
        showEmpty(stored);
        emptyToggle.addEventListener('change', function () {
            try {
                window.sessionStorage.setItem(EMPTY_KEY, emptyToggle.checked ? '1' : '0');
            } catch (error) {
                /* the toggle still applies for this page */
            }
            showEmpty(emptyToggle.checked);
        });
    }

    function caretInside(node) {
        var active = document.activeElement;
        return !!(active && node && (node === active || node.contains(active)));
    }

    function chapterHeading(chapter) {
        var heading = chapter.previousElementSibling;
        if (heading && /^H[2-4]$/.test(heading.tagName)) {
            return heading;
        }
        return null;
    }

    function liftOut(chapter) {
        var group = chapter.closest('[data-vacant-group]');
        if (!group) {
            return;
        }
        var heading = chapterHeading(chapter);
        if (heading && heading.parentNode === group) {
            heading.classList.remove('is-filled');
            group.parentNode.insertBefore(heading, group);
        }
        chapter.classList.remove('is-filled');
        group.parentNode.insertBefore(chapter, group);
        if (!group.children.length) {
            group.remove();
        }
    }

    function holdUntilBlur(chapter) {
        chapter.setAttribute('data-hold-vacant', '1');
    }

    window.DrefEmptySections = {
        sync: function (chapter, hasText) {
            if (!chapter) {
                return;
            }
            var group = chapter.closest('[data-vacant-group]');
            var heading = chapterHeading(chapter);
            if (hasText) {
                chapter.removeAttribute('data-vacant');
                chapter.classList.add('is-filled');
                if (heading && heading.hasAttribute('data-vacant')) {
                    heading.removeAttribute('data-vacant');
                    heading.classList.add('is-filled');
                }
                if (!group) {
                    chapter.removeAttribute('data-hold-vacant');
                    return;
                }
                // Moving the field out of the empty group blurs it. Leave it where the
                // caret is until editing finishes, and only then lift it into the document.
                if (caretInside(chapter)) {
                    holdUntilBlur(chapter);
                    return;
                }
                chapter.removeAttribute('data-hold-vacant');
                liftOut(chapter);
                return;
            }
            chapter.classList.remove('is-filled');
            chapter.setAttribute('data-vacant', '1');
            if (heading) {
                heading.classList.remove('is-filled');
            }
            if (caretInside(chapter)) {
                holdUntilBlur(chapter);
                return;
            }
            chapter.removeAttribute('data-hold-vacant');
            if (group) {
                return;
            }
            var wrap = document.createElement('div');
            wrap.className = 'dref-vacant';
            wrap.setAttribute('data-vacant-group', '');
            var before = chapter.previousElementSibling;
            if (before && /^H[2-4]$/.test(before.tagName)) {
                before.setAttribute('data-vacant', '1');
                before.parentNode.insertBefore(wrap, before);
                wrap.appendChild(before);
            } else {
                chapter.parentNode.insertBefore(wrap, chapter);
            }
            wrap.appendChild(chapter);
        }
    };

    document.addEventListener('focusout', function (event) {
        var chapter = event.target && event.target.closest ? event.target.closest('.dref-chapter--inline[data-hold-vacant]') : null;
        if (!chapter || !window.DrefEmptySections) {
            return;
        }
        window.setTimeout(function () {
            if (!chapter.hasAttribute('data-hold-vacant') || caretInside(chapter)) {
                return;
            }
            var body = chapter.querySelector('[data-chapter-body]');
            var text = body ? body.textContent.replace(/\u00a0/g, ' ').trim() : '';
            window.DrefEmptySections.sync(chapter, !!text);
        }, 0);
    });

    var A = window.AdminUnderlineTabs;
    var root = document.getElementById('dref-draft-tabs');
    if (!root || !A) {
        return;
    }

    function activate(tabId) {
        A.activateStripTab('#dref-draft-tabs', tabId, { panelSelector: '#dref-draft-panels .settings-panel' });
        try {
            var url = new URL(window.location.href);
            if (tabId === 'narrative') url.searchParams.delete('tab');
            else url.searchParams.set('tab', tabId);
            window.history.replaceState(null, '', url.pathname + url.search);
        } catch (e) { /* ignore */ }
    }

    root.querySelectorAll('.settings-tab').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var tabId = this.getAttribute('data-tab');
            if (tabId) activate(tabId);
        });
    });
})();
