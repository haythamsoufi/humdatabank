/**
 * Download the currently visible documentation page as a server-rendered PDF.
 */

(function() {
    'use strict';

    var isExporting = false;

    function sanitizeFilename(name) {
        var cleaned = (name || 'Documentation')
            .replace(/[\\/:*?"<>|]/g, '')
            .replace(/\s+/g, ' ')
            .trim()
            .replace(/\.+$/, '');
        return (cleaned || 'Documentation').substring(0, 120);
    }

    function getExportPdfUrl() {
        var path = window.location.pathname || '';
        if (path.length > 1 && path.charAt(path.length - 1) === '/') {
            path = path.slice(0, -1);
        }
        return path + '/export.pdf';
    }

    function isPlaceholderFilename(name) {
        if (!name) return true;
        var stem = name.replace(/\.pdf$/i, '');
        return !stem || /^[\s_.-]+$/.test(stem);
    }

    function parseFilenameFromDisposition(header) {
        if (!header) return null;
        var utf8Match = /filename\*=UTF-8''([^;\s]+)/i.exec(header);
        if (utf8Match) {
            try {
                return decodeURIComponent(utf8Match[1].replace(/\+/g, ' '));
            } catch (e) {
                /* fall through */
            }
        }
        var quoted = /filename="([^"]+)"/i.exec(header);
        if (quoted && !isPlaceholderFilename(quoted[1])) {
            return quoted[1];
        }
        var plain = /filename=([^;\s]+)/i.exec(header);
        if (plain && !isPlaceholderFilename(plain[1])) {
            return plain[1].replace(/^"|"$/g, '');
        }
        return null;
    }

    function setButtonState(button, exporting) {
        if (!button) return;
        button.disabled = exporting;
        button.setAttribute('aria-busy', exporting ? 'true' : 'false');
        var label = button.querySelector('[data-export-label]');
        var busy = button.querySelector('[data-export-busy]');
        if (label) label.hidden = exporting;
        if (busy) busy.hidden = !exporting;
    }

    function triggerDownload(blob, filename) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function() {
            URL.revokeObjectURL(url);
        }, 0);
    }

    async function exportCurrentDoc() {
        if (isExporting) return;

        var button = document.getElementById('docs-export-pdf-btn');
        var titleEl = document.querySelector('.docs-content-title');
        var exportUrl = getExportPdfUrl();

        isExporting = true;
        setButtonState(button, true);

        try {
            var fn = (window.getFetch && window.getFetch()) || fetch;
            var response = await fn(exportUrl, {
                method: 'GET',
                credentials: 'same-origin'
            });

            if (!response.ok) {
                var message = 'PDF export failed. Please try again.';
                if (response.status === 503) {
                    message = 'PDF generation is not available on this server.';
                }
                throw new Error(message);
            }

            var blob = await response.blob();
            var filename = parseFilenameFromDisposition(response.headers.get('Content-Disposition'));
            if (!filename) {
                filename = sanitizeFilename(titleEl && titleEl.textContent) + '.pdf';
            }
            triggerDownload(blob, filename);
        } catch (err) {
            console.error('Documentation PDF export failed:', err);
            if (window.showToast) {
                window.showToast(err.message || 'PDF export failed. Please try again.', 'error');
            } else {
                window.alert(err.message || 'PDF export failed. Please try again.');
            }
        } finally {
            isExporting = false;
            setButtonState(button, false);
        }
    }

    function init() {
        var button = document.getElementById('docs-export-pdf-btn');
        if (!button) return;

        button.addEventListener('click', function(e) {
            e.preventDefault();
            exportCurrentDoc();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.DocsPdfExport = {
        exportCurrentDoc: exportCurrentDoc,
        getExportPdfUrl: getExportPdfUrl
    };
})();
