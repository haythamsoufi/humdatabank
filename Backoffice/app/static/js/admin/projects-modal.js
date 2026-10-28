/**
 * Project edit modal (Admin → Projects and Explore Data → NSD funds).
 */
(function () {
    'use strict';

    var modalCtrl = null;

    function getCsrf() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
        var input = document.querySelector('input[name="csrf_token"]');
        return input ? input.value : '';
    }

    function fetchFn() {
        return (window.getFetch && window.getFetch()) || fetch;
    }

    function partialUrl(baseUrl) {
        var u = baseUrl || '';
        return u + (u.indexOf('?') >= 0 ? '&' : '?') + 'partial=1';
    }

    function setModalTitle(title) {
        var el = document.getElementById('projectEditModal-title');
        if (el && title) el.textContent = title;
    }

    function ensureModalController() {
        var shell = document.getElementById('projectEditModal');
        if (!shell) return null;
        if (!modalCtrl && window.ModalUtils) {
            modalCtrl = window.ModalUtils.makeModal(shell, {
                closeSelector: '.close-modal, [data-project-modal-dismiss]',
            });
        }
        return shell;
    }

    function resetModalScroll(shell) {
        if (!shell) return;
        shell.scrollTop = 0;
        var content = shell.querySelector('.modal-content');
        if (content) content.scrollTop = 0;
        var panel = shell.querySelector('.modal-shell-content');
        if (panel) panel.scrollTop = 0;
    }

    function openModalShell() {
        var shell = ensureModalController();
        if (!shell) return;
        if (modalCtrl && modalCtrl.openModal) {
            modalCtrl.openModal();
        } else {
            shell.classList.remove('hidden');
        }
        resetModalScroll(shell);
    }

    function closeModalShell() {
        if (modalCtrl && modalCtrl.closeModal) {
            modalCtrl.closeModal();
        } else {
            var shell = document.getElementById('projectEditModal');
            if (shell) shell.classList.add('hidden');
        }
    }

    function wireProjectForm(root) {
        if (!root) return;
        var form = root.querySelector('form[data-project-form]');
        if (!form || form.dataset.projectWired === '1') return;
        form.dataset.projectWired = '1';

        var titleNode = root.querySelector('[data-project-modal-title]');
        if (titleNode) {
            setModalTitle(titleNode.getAttribute('data-project-modal-title'));
        }

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            var action = form.getAttribute('action') || '';
            var body = new FormData(form);
            fetchFn()(action, {
                method: 'POST',
                body: body,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    Accept: 'application/json',
                },
                credentials: 'same-origin',
            })
                .then(function (r) {
                    return r.json().then(function (data) {
                        return { ok: r.ok, status: r.status, body: data };
                    }).catch(function () {
                        return { ok: r.ok, status: r.status, body: {} };
                    });
                })
                .then(function (out) {
                    if (out.ok && out.body && out.body.success === true) {
                        closeModalShell();
                        window.location.reload();
                        return;
                    }
                    if (out.body && out.body.form_html) {
                        openProjectEditFromHtml(out.body.form_html);
                        return;
                    }
                    var msg = (out.body && (out.body.error || out.body.message)) || 'Could not save the project.';
                    if (window.__clientWarn) window.__clientWarn(String(msg));
                })
                .catch(function () {
                    if (window.__clientWarn) window.__clientWarn('Could not save the project.');
                });
        });

        root.querySelectorAll('[data-project-modal-dismiss]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                closeModalShell();
            });
        });

        var delBtn = root.querySelector('.project-modal-delete');
        if (delBtn) {
            delBtn.addEventListener('click', function () {
                var u = delBtn.getAttribute('data-project-delete-url');
                if (!u) return;
                if (!window.confirm('Delete this project?')) return;
                fetchFn()(u, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': getCsrf(),
                        'X-Requested-With': 'XMLHttpRequest',
                        Accept: 'application/json',
                    },
                    credentials: 'same-origin',
                })
                    .then(function (r) {
                        return r.json().catch(function () {
                            return {};
                        });
                    })
                    .then(function (data) {
                        if (data && data.success === true) {
                            closeModalShell();
                            window.location.reload();
                        } else {
                            var msg = (data && (data.error || data.message)) || 'Could not delete the project.';
                            if (window.__clientWarn) window.__clientWarn(String(msg));
                        }
                    });
            });
        }
    }

    function openProjectEditFromHtml(html) {
        var bodyEl = document.getElementById('projectEditModalBody');
        if (!bodyEl) return;
        bodyEl.innerHTML = html;
        wireProjectForm(bodyEl);
        openModalShell();
    }

    function openProjectEditWithFetch(url) {
        var bodyEl = document.getElementById('projectEditModalBody');
        if (!bodyEl || !url) return;
        bodyEl.innerHTML =
            '<p class="text-sm text-gray-500 flex items-center gap-2">' +
            '<i class="fas fa-spinner fa-spin text-gray-400" aria-hidden="true"></i>Loading…</p>';
        openModalShell();
        fetchFn()(partialUrl(url), {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
            credentials: 'same-origin',
        })
            .then(function (r) {
                if (!r.ok) throw new Error('load failed');
                return r.text();
            })
            .then(function (html) {
                openProjectEditFromHtml(html);
            })
            .catch(function () {
                closeModalShell();
                if (window.__clientWarn) window.__clientWarn('Could not load the project form.');
            });
    }

    function onDocumentClick(e) {
        var trigger = e.target.closest('[data-project-edit]');
        if (!trigger) return;
        e.preventDefault();
        var url = trigger.getAttribute('data-project-edit') || trigger.getAttribute('href');
        if (url) openProjectEditWithFetch(url);
    }

    document.addEventListener('click', onDocumentClick);

    window.ProjectEditModal = {
        open: openProjectEditWithFetch,
        openFromHtml: openProjectEditFromHtml,
    };

    document.addEventListener('DOMContentLoaded', function () {
        var host = document.querySelector('[data-open-project-edit]');
        if (!host) return;
        var initial = host.getAttribute('data-open-project-edit');
        var base = host.getAttribute('data-project-edit-url-template');
        if (initial && base) {
            openProjectEditWithFetch(base.replace('__ID__', String(initial)));
        }
    });
})();
