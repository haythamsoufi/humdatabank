/**
 * Chatbot HtmlPipeline module
 * @module chatbot/html-pipeline
 */

export const HtmlPipelineMixin = {
    escapeHtml(text) {
        if (typeof text !== 'string') return '';
        return String(text == null ? '' : text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },

    _safeCodePoint(cp, fallback) {
        if (!Number.isFinite(cp) || cp < 0 || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF)) return fallback;
        return String.fromCodePoint(cp);
    },

    _safeSameOriginUrl(rawHref) {
        try {
            const href = String(rawHref == null ? '' : rawHref).trim();
            if (!href) return null;
            if (href.startsWith('#')) return href;
            if (href.startsWith('/')) return href;
            const url = new URL(href, window.location.href);
            if (!window.location || !window.location.origin) return null;
            if (url.origin !== window.location.origin) return null;
            return url.pathname + url.search + url.hash;
        } catch (_) {
            return null;
        }
    },

    /**
     * Decode HTML entities so backend-escaped content (e.g. &lt;strong&gt;, &lt;br&gt;)
     * renders as HTML instead of showing raw tags. Run before sanitizeHtml.
     */

    decodeHtmlEntities(html) {
        if (typeof html !== 'string') return '';
        return html
            .replace(/&amp;/g, '&')
            .replace(/&lt;/g, '<')
            .replace(/&gt;/g, '>')
            .replace(/&quot;/g, '"')
            .replace(/&#39;/g, "'")
            .replace(/&#x27;/g, "'")
            .replace(/&#(\d+);/g, (m, n) => this._safeCodePoint(parseInt(n, 10), m))
            .replace(/&#x([0-9a-fA-F]+);/g, (m, n) => this._safeCodePoint(parseInt(n, 16), m));
    },
    /**
     * Linkify markdown-style links [label](url) in cell content. Escapes HTML first, then
     * converts links. Used for table cells so document links become clickable.
     */

    _linkifyCellContent(cell) {
        if (cell == null || cell === '') return '';
        const escaped = this.escapeHtml(String(cell));
        const mdLinkRe = /\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g;
        return escaped.replace(mdLinkRe, (_, label, href) => {
            const safe = this._safeSameOriginUrl(href);
            if (!safe) return this.escapeHtml(label || '');
            return '<a href="' + this.escapeHtml(safe) + '" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">' + this.escapeHtml(label || '') + '</a>';
        });
    },
    /**
     * Convert markdown table blocks (e.g. "| A | B |\n|---|---|\n| 1 | 2 |") to HTML tables.
     * Handles optional trailing pipe so "| A | B" works. Safe: cell content is escaped and linkified.
     */

    markdownTablesToHtml(text) {
        if (typeof text !== 'string') return '';
        let normalized = String(text || '');
        const inputLength = normalized.length;
        const stripInvisible = (s) => String(s == null ? '' : s)
            .replace(/[\u0000-\u001F\u007F-\u009F\u00AD\u061C\u200B-\u200F\u202A-\u202E\u2060\u2066-\u2069\uFEFF]/g, '');
        const stripHtmlBreaks = (s) => String(s == null ? '' : s).replace(/<br\s*\/?>/gi, '');
        const normalizeDashAndSpace = (s) => stripInvisible(s)
            .replace(/<br\s*\/?>/gi, '')
            .replace(/[—–−]/g, '-')
            .replace(/\u00A0/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
        const splitMarkdownRow = (ln) => {
            const lnNorm = normalizeDashAndSpace(stripHtmlBreaks(ln));
            const parts = lnNorm.split('|').map((s) => normalizeDashAndSpace(s));
            let start = 0;
            let end = parts.length;
            while (start < end && !parts[start]) start++;
            while (end > start && !parts[end - 1]) end--;
            return parts.slice(start, end);
        };
        // Normalize line endings first so markdown rows are split consistently.
        normalized = normalized.replace(/\r\n?/g, '\n');
        // Some persisted responses can contain literal "\n" sequences.
        if (!normalized.includes('\n') && /\\n/.test(normalized) && /\|/.test(normalized)) {
            normalized = normalized.replace(/\\n/g, '\n');
        }
        const lines = normalized.split('\n');
        const out = [];
        let i = 0;
        let candidateBlocks = 0;
        let renderedTables = 0;
        const separatorCellLooksValid = (cell) => {
            const raw = normalizeDashAndSpace(cell);
            // Normalize common invisible/unicode chars that can appear in streamed text.
            const cleaned = raw
                .replace(/\s+/g, '')
                .trim();
            // Markdown separator cell: --- , :--- , ---: , :---:
            return /^:?-{3,}:?$/.test(cleaned);
        };
        const separatorLineLooksValid = (line) => {
            const raw = normalizeDashAndSpace(stripHtmlBreaks(line));
            if (!raw || raw.indexOf('|') === -1) return false;
            const syntaxOnly = raw.replace(/[|:\-\s]/g, '');
            if (syntaxOnly) return false;
            return ((raw.match(/\|/g) || []).length >= 2) && ((raw.match(/-/g) || []).length >= 3);
        };
        const separatorRowLooksValid = (row, expectedCols) => {
            if (!Array.isArray(row) || row.length < 2) return false;
            if (Number.isFinite(expectedCols) && expectedCols > 0 && row.length !== expectedCols) return false;
            return row.every((cell) => separatorCellLooksValid(cell));
        };
        const looksLikeTableLine = (line) => {
            const trimmed = String(line || '').trim();
            if (!trimmed) return false;
            // Ignore rendered HTML tags; only process markdown-ish lines.
            if (trimmed.startsWith('<') && trimmed.endsWith('>')) return false;
            if (/^\s*\|/.test(line)) return true;
            // Support rows without leading/trailing pipes: "A | B | C"
            const pipeCount = (trimmed.match(/\|/g) || []).length;
            return pipeCount >= 2;
        };
        while (i < lines.length) {
            const line = lines[i];
            if (!looksLikeTableLine(line)) {
                out.push(line);
                i++;
                continue;
            }
            const block = [];
            while (i < lines.length && looksLikeTableLine(lines[i])) {
                block.push(lines[i]);
                i++;
            }
            candidateBlocks++;
            if (block.length < 2) {
                out.push(...block);
                continue;
            }
            const rows = block.map((ln) => splitMarkdownRow(ln));
            // Find the first valid markdown separator row anywhere in the block,
            // then treat the previous row as header. This is resilient to
            // pipe-containing preface lines that can appear in stored messages.
            let sepIndex = -1;
            for (let r = 1; r < rows.length; r++) {
                const prev = rows[r - 1] || [];
                const cur = rows[r] || [];
                if ((prev.length >= 2) && separatorRowLooksValid(cur, prev.length)) {
                    sepIndex = r;
                    break;
                }
            }
            // Fallback: separator may include odd chars that survive cell parsing; test raw line.
            if (sepIndex < 1) {
                for (let r = 1; r < block.length; r++) {
                    const prev = rows[r - 1] || [];
                    if (prev.length < 2) continue;
                    if (separatorLineLooksValid(block[r])) {
                        sepIndex = r;
                        break;
                    }
                }
            }
            if (sepIndex < 1) {
                const rejectPayload = {
                    block_preview: block.slice(0, 4),
                    header_cells: rows[0] || [],
                    separator_cells: rows[1] || [],
                    header_len: rows[0] ? rows[0].length : 0,
                    separator_len: rows[1] ? rows[1].length : 0,
                    separator_valid_flags: (rows[1] || []).map((c) => separatorCellLooksValid(c)),
                    separator_line_raw_valid: separatorLineLooksValid(block[1] || ''),
                };
                this._warn('Markdown table block rejected:', rejectPayload);
                out.push(...block);
                continue;
            }
            const headerRow = rows[sepIndex - 1] || [];
            const headerCols = headerRow.length;
            const separatorRow = rows[sepIndex] || [];
            const colAligns = separatorRow.map(cell => {
                const c = normalizeDashAndSpace(cell).replace(/\s+/g, '');
                if (c.startsWith(':') && c.endsWith(':')) return 'center';
                if (c.endsWith(':')) return 'right';
                return '';
            });
            while (colAligns.length < headerCols) colAligns.push('');
            const bodyRows = rows.length > (sepIndex + 1) ? rows.slice(sepIndex + 1) : [];
            let table = '<table class="chat-ai-table"><thead><tr>';
            headerRow.forEach((cell, ci) => {
                const align = colAligns[ci] ? ' style="text-align:' + colAligns[ci] + '"' : '';
                table += '<th' + align + '>' + this._linkifyCellContent(cell || '') + '</th>';
            });
            table += '</tr></thead><tbody>';
            bodyRows.forEach(row => {
                const adjusted = (row || []).slice(0, headerCols);
                while (adjusted.length < headerCols) adjusted.push('');
                table += '<tr>';
                adjusted.forEach((cell, ci) => {
                    const align = colAligns[ci] ? ' style="text-align:' + colAligns[ci] + '"' : '';
                    table += '<td' + align + '>' + this._linkifyCellContent(cell || '') + '</td>';
                });
                table += '</tr>';
            });
            table += '</tbody></table>';
            out.push(table);
            renderedTables++;
        }
        this._tableDebugLog('Markdown table formatting:', {
            input_length: inputLength,
            lines: lines.length,
            candidate_blocks: candidateBlocks,
            rendered_tables: renderedTables
        });
        return out.join('\n');
    },
    /**
     * Turn one markdown source line into a structured <li data-source-*>.
     * The chip is the only Sources UI; prose is never left as a disclosure.
     */
    _sourceLineToListItemHtml(line) {
        const raw = String(line || '').replace(/^\s*(?:[-*•]|\d{1,3}[.)])\s+/, '').trim();
        if (!raw || /^(?:#{1,6}\s*)?sources\s*:?$/i.test(raw)) return '';
        let title = raw;
        let url = '';
        let detail = '';
        const link = raw.match(/\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/);
        if (link) {
            title = (link[1] || '').trim() || raw;
            const safe = this._safeSameOriginUrl(link[2]);
            url = safe || '';
            detail = raw.slice(link.index + link[0].length).replace(/^[\s:—–-]+/, '').trim();
        }
        const attrs = [
            `data-source-title="${this.escapeHtml(title)}"`,
            'data-source-kind="other"',
        ];
        if (detail) attrs.push(`data-source-detail="${this.escapeHtml(detail)}"`);
        if (url) attrs.push(`data-source-url="${this.escapeHtml(url)}"`);
        const label = this.escapeHtml(title);
        const inner = url
            ? `<a href="${this.escapeHtml(url)}" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">${label}</a>`
            : label;
        const withDetail = detail ? `${inner}: ${this.escapeHtml(detail)}` : inner;
        return `<li ${attrs.join(' ')}>${withDetail}</li>`;
    },

    /**
     * If text contains a Sources heading, package it as structured rows.
     * Title/detail come from these data-* attrs or meta.sources.
     */
    markdownSourcesToHtml(text) {
        if (typeof text !== 'string') return text;
        if (text.includes('chat-response-sources') && text.includes('chat-response-sources-body')) {
            return text;
        }
        if (!/^(?:#{2,3}\s*)?Sources\s*:?\s*$/im.test(text)) {
            return text;
        }
        const stopAt = '(?=\\n\\s*\\n\\s*(?:If you want, I can|If you\'d like|Which would you prefer\\?|Which format do you prefer\\?|\\*\\*Notes?\\s*\\/\\s*next steps\\b)|\\n\\s*(?:If you want, I can|If you\'d like)|$(?![\\s\\S]))';
        const sourcesRegex = new RegExp('^((?:#{2,3}\\s*)?Sources\\s*:?\\s*)\\s*$(.+?)' + stopAt, 'ims');
        const sourcesMatch = text.match(sourcesRegex);
        if (!sourcesMatch) return text;
        const sourcesBlockRaw = sourcesMatch[2].trim();
        const mainPart = text.slice(0, sourcesMatch.index).trim();
        const lis = sourcesBlockRaw.split(/\n+/).map((line) => this._sourceLineToListItemHtml(line)).filter(Boolean);
        if (!lis.length) return mainPart;
        const sourcesHtml = (
            '<div class="chat-response-sources">' +
            '<div class="chat-response-sources-body">' +
            `<ul class="chat-response-sources-list">${lis.join('')}</ul>` +
            '</div></div>'
        );
        return mainPart + '\n\n' + sourcesHtml;
    },

    // Enhanced HTML sanitization for AI responses

    sanitizeHtml(html) {
        if (typeof html !== 'string') return '';
        const originalHtml = String(html || '');

        // Decode entities first so escaped markdown (e.g., &lt; and &#124;) can be parsed.
        html = this.decodeHtmlEntities(html);

        // Parse ## Sources from markdown so sources are always a proper block (fixes markdown from DB on refresh)
        html = this.markdownSourcesToHtml(html);

        // Convert markdown tables to HTML so they render as tables (backend may send markdown or we get raw from history)
        html = this.markdownTablesToHtml(html);

        // Normalize bullets: avoid "• - " (double bullet) and orphan "•" on its own
        html = html.replace(/•\s*-\s+/g, '• ');
        html = html.replace(/(<br\s*\/?>)\s*•\s*(<br\s*\/?>|$)/gi, '$1$2');

        // Parse into a detached document without assigning innerHTML
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const tempDiv = doc.body;
        if (!tempDiv) return '';

        // Remove all script tags and event handlers
        const scripts = tempDiv.getElementsByTagName('script');
        for (let i = scripts.length - 1; i >= 0; i--) {
            scripts[i].parentNode.removeChild(scripts[i]);
        }

        // Remove dangerous protocols and all event handler attributes
        const allElements = tempDiv.getElementsByTagName('*');
        for (let i = allElements.length - 1; i >= 0; i--) {
            const element = allElements[i];

            // Remove dangerous protocols from any attributes
            for (let j = element.attributes.length - 1; j >= 0; j--) {
                const attr = element.attributes[j];
                const v = (attr.value || '').toLowerCase().trim();
                if (!v) continue;
                // Only URL-bearing attributes need protocol checks; the tag/attribute
                // allowlist and link validation below do the rest.
                const n = attr.name.toLowerCase();
                if (
                    (n === 'href' || n === 'src' || n === 'xlink:href' || n === 'action' || n === 'formaction') &&
                    /^\s*(?:javascript|data|vbscript|file|about):/i.test(v.replace(/[\u0000-\u001F\u007F\s]+/g, ''))
                ) {
                    element.removeAttribute(attr.name);
                }
            }

            // Remove event handler and style attributes
            for (let j = element.attributes.length - 1; j >= 0; j--) {
                const attr = element.attributes[j];
                const attrName = attr.name.toLowerCase();
                if (attrName.startsWith('on') || attrName === 'style') {
                    element.removeAttribute(attr.name);
                }
            }
        }

        // Only allow safe HTML tags (including <a> for links, table for data, details/summary for collapsible Sources)
        const allowedTags = ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'details', 'summary'];
        const allTags = tempDiv.getElementsByTagName('*');

        for (let i = allTags.length - 1; i >= 0; i--) {
            const element = allTags[i];
            if (!allowedTags.includes(element.tagName.toLowerCase())) {
                // Replace unsafe tags with their text content
                const textNode = document.createTextNode(element.textContent);
                element.parentNode.replaceChild(textNode, element);
            }
        }

        // Ensure every <table> has chat-ai-table so model-generated HTML tables are styled like markdown-rendered ones
        const tables = tempDiv.getElementsByTagName('table');
        for (let t = 0; t < tables.length; t++) {
            const tbl = tables[t];
            if (tbl.classList && !tbl.classList.contains('chat-ai-table')) {
                tbl.classList.add('chat-ai-table');
            }
        }

        // Attribute allowlist + safe links only
        const allowedAttrsByTag = {
            a: new Set(['href', 'title', 'class', 'target', 'rel']), // target/rel for new-tab links
            table: new Set(['class']),
            thead: new Set(['class']),
            tbody: new Set(['class']),
            tr: new Set(['class']),
            th: new Set(['class']),
            td: new Set(['class']),
            details: new Set(['class']),
            summary: new Set(['class']),
            div: new Set(['class']),
            span: new Set(['class']),
            ul: new Set(['class']),
            ol: new Set(['class']),
            // Structured source rows. Without these, the chip formatter cannot
            // see titles and leaves the native <details> disclosure in place.
            li: new Set([
                'class',
                'data-source-title',
                'data-source-kind',
                'data-source-detail',
                'data-source-url',
                'data-source-page',
            ]),
        };
        const allTags2 = tempDiv.getElementsByTagName('*');
        for (let i = allTags2.length - 1; i >= 0; i--) {
            const el = allTags2[i];
            const tag = el.tagName.toLowerCase();
            const allowed = allowedAttrsByTag[tag] || new Set();

            // Clean attributes
            for (let j = el.attributes.length - 1; j >= 0; j--) {
                const attr = el.attributes[j];
                if (!allowed.has(attr.name.toLowerCase())) {
                    el.removeAttribute(attr.name);
                }
            }

            // Special-case: safe href for links (same-origin/relative only)
            if (tag === 'a') {
                const href = el.getAttribute('href') || '';
                let safe;
                if (window.SafeDom) {
                    safe = window.SafeDom.safeUrl(href, { allowSameOrigin: true });
                } else {
                    safe = this._safeSameOriginUrl(href);
                }
                if (!safe) {
                    el.removeAttribute('href');
                } else {
                    el.setAttribute('href', safe);
                }
                if (el.hasAttribute('target')) {
                    el.setAttribute('target', '_blank');
                    el.setAttribute('rel', 'noopener noreferrer');
                } else {
                    el.removeAttribute('rel');
                }
            }
        }
        this._enhanceIndicatorActionLinks(tempDiv);
        const finalHtml = tempDiv.innerHTML;
        const tableCount = (finalHtml.match(/<table\b/gi) || []).length;
        this._tableDebugLog('sanitizeHtml result:', {
            input_length: originalHtml.length,
            output_length: finalHtml.length,
            tables_found: tableCount,
            contains_pipe_chars: /\|/.test(originalHtml)
        });
        return finalHtml;
    },

    _tableToMatrix(tableEl) {
        if (!tableEl || tableEl.tagName !== 'TABLE') return [];
        const out = [];
        const trs = tableEl.querySelectorAll('tr');
        trs.forEach((tr) => {
            // Skip UI-only "expand" control row that appears in immersive mode
            if (tr.classList && tr.classList.contains('chat-ai-table-expand-row')) return;
            const cells = tr.querySelectorAll('th, td');
            const values = Array.from(cells).map((cell) => (cell.textContent || '').trim());
            if (values.length) out.push(values);
        });
        return out;
    },

    async _downloadTableAsExcel(tableEl) {
        if (!tableEl || tableEl.tagName !== 'TABLE') return;
        const rows = this._tableToMatrix(tableEl);
        if (!rows || !rows.length) return;

        let resp;
        try {
            resp = await this._apiFetch('/api/ai/v2/table/export', {
                method: 'POST',
                body: JSON.stringify({ rows })
            });
        } catch (_e) {
            return;
        }

        if (!resp || !resp.ok) return;
        const blob = await resp.blob();
        const filename = resp.headers.get('X-hum-databank-Export-Filename') || 'table-data.xlsx';

        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    },

    _addTableCopyButtons(container) {
        if (!container || typeof container.querySelectorAll !== 'function') return;
        const tables = container.querySelectorAll('.chat-ai-table');
        tables.forEach((table) => {
            if (table.closest('.chat-ai-table-wrapper')) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-ai-table-wrapper';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'chat-ai-table-copy-btn';
            btn.setAttribute('aria-label', 'Download table as Excel');
            btn.title = 'Download table as Excel spreadsheet';
            btn.innerHTML = '<i class="fas fa-file-excel" aria-hidden="true"></i><span>Download Excel</span>';
            btn.addEventListener('click', async () => {
                await this._downloadTableAsExcel(table);
                const span = btn.querySelector('span');
                const orig = span ? span.textContent : '';
                if (span) span.textContent = 'Downloaded!';
                btn.classList.add('chat-ai-table-copy-done');
                setTimeout(() => {
                    if (span) span.textContent = orig;
                    btn.classList.remove('chat-ai-table-copy-done');
                }, 1500);
            });
            wrapper.insertBefore(btn, table);
        });
    },

    _collapseLongTables(container) {
        if (!container || !this._isImmersive()) return;
        const DEFAULT_VISIBLE_ROWS = 5;
        const tables = container.querySelectorAll('.chat-ai-table');
        tables.forEach((table) => {
            if (table.classList.contains('chat-ai-table-collapsible')) return;
            const tbody = table.querySelector('tbody');
            if (!tbody) return;
            const trs = Array.from(tbody.querySelectorAll('tr'));
            if (trs.length <= DEFAULT_VISIBLE_ROWS) return;
            const firstRow = table.querySelector('tr');
            const colCount = firstRow ? firstRow.querySelectorAll('th, td').length : 1;
            table.classList.add('chat-ai-table-collapsible');
            for (let i = DEFAULT_VISIBLE_ROWS; i < trs.length; i++) {
                trs[i].classList.add('chat-ai-table-row-hidden');
            }
            const expandTr = document.createElement('tr');
            expandTr.className = 'chat-ai-table-expand-row';
            expandTr.setAttribute('role', 'button');
            expandTr.setAttribute('tabIndex', '0');
            expandTr.setAttribute('aria-label', 'Show more rows');
            const expandTd = document.createElement('td');
            expandTd.colSpan = colCount;
            expandTd.innerHTML = '<span class="chat-ai-table-expand-label">Show ' + (trs.length - DEFAULT_VISIBLE_ROWS) + ' more rows</span> <i class="fas fa-chevron-down chat-ai-table-expand-icon" aria-hidden="true"></i>';
            expandTr.appendChild(expandTd);
            tbody.appendChild(expandTr);
            expandTr.addEventListener('click', () => {
                tbody.querySelectorAll('.chat-ai-table-row-hidden').forEach((tr) => tr.classList.remove('chat-ai-table-row-hidden'));
                expandTr.remove();
                table.classList.remove('chat-ai-table-collapsible');
                table.classList.add('chat-ai-table-expanded');
            });
            expandTr.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    expandTr.click();
                }
            });
        });
    },

    _normalizeSourcesSection(container) {
        if (!container || typeof container.querySelector !== 'function') return;
        const _buildSourcesBody = (items) => {
            const body = document.createElement('div');
            body.className = 'chat-response-sources-body';
            items.forEach((li, idx) => {
                if (idx > 0) body.appendChild(document.createElement('br'));
                // Clone child nodes (preserves safe links) instead of re-injecting raw innerHTML
                Array.from(li.childNodes).forEach(n => body.appendChild(n.cloneNode(true)));
            });
            return body;
        };

        const headings = container.querySelectorAll('h1, h2, h3, h4');
        headings.forEach((heading) => {
            const title = (heading.textContent || '').trim().toLowerCase();
            if (title !== 'sources') return;
            const list = heading.nextElementSibling;
            if (!list || !/^(?:UL|OL)$/i.test(list.tagName)) return;
            const items = Array.from(list.children).filter((c) => c.tagName === 'LI');
            if (!items.length) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-response-sources';
            wrapper.appendChild(_buildSourcesBody(items));
            heading.parentNode.insertBefore(wrapper, heading);
            heading.remove();
            list.remove();
        });

        // Also normalize non-heading variants:
        // <p>Sources</p><ul>...</ul> or <p><strong>Sources:</strong></p><ol>...</ol>
        const paragraphs = container.querySelectorAll('p');
        paragraphs.forEach((p) => {
            const title = (p.textContent || '').trim().toLowerCase().replace(/:$/, '');
            if (title !== 'sources') return;
            const list = p.nextElementSibling;
            if (!list || !/^(?:UL|OL)$/i.test(list.tagName)) return;
            const items = Array.from(list.children).filter((c) => c.tagName === 'LI');
            if (!items.length) return;
            const wrapper = document.createElement('div');
            wrapper.className = 'chat-response-sources';
            wrapper.appendChild(_buildSourcesBody(items));
            p.parentNode.insertBefore(wrapper, p);
            p.remove();
            list.remove();
        });
    },

    _squashPlain(text) {
        return String(text || '').replace(/\s+/g, ' ').trim();
    },

    _isAnswerVerificationCaveatText(plain) {
        const t = this._squashPlain(plain).toLowerCase();
        if (!t) return false;
        if (t.includes('could not be verified against the available sources')) return true;
        if ((t.startsWith('note:') || t.startsWith('> note:')) && t.includes('could not be verified')) return true;
        return false;
    },

    /**
     * When message meta includes structured sources[] but the HTML body lacks
     * data-* attrs, rewrite the sources body so the chip can use attrs.
     */
    _injectStructuredSourcesFromMeta(container, sources) {
        try {
            if (!container || !Array.isArray(sources) || !sources.length) return;
            if (container.querySelector('[data-source-title]')) return;

            const escapeAttr = (v) => String(v ?? '')
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            const escapeText = escapeAttr;

            const lis = sources.map((raw) => {
                if (!raw || typeof raw !== 'object') return '';
                const title = String(raw.title || '').trim();
                if (!title) return '';
                const detail = String(raw.detail || raw.excerpt || '').trim();
                const url = String(raw.url || '').trim();
                const page = raw.page != null && raw.page !== '' ? String(raw.page) : '';
                const kind = String(raw.kind || raw.type || 'other').trim() || 'other';
                const attrs = [
                    `data-source-title="${escapeAttr(title)}"`,
                    `data-source-kind="${escapeAttr(kind)}"`,
                ];
                if (detail) attrs.push(`data-source-detail="${escapeAttr(detail)}"`);
                if (url) attrs.push(`data-source-url="${escapeAttr(url)}"`);
                if (page) attrs.push(`data-source-page="${escapeAttr(page)}"`);
                let inner = escapeText(title);
                if (page) inner += ` — page ${escapeText(page)}`;
                if (detail) inner += `: ${escapeText(detail)}`;
                if (url && url.startsWith('/')) {
                    inner = `<a href="${escapeAttr(url)}" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">${escapeText(title)}${page ? ` — page ${escapeText(page)}` : ''}</a>${detail ? `: ${escapeText(detail)}` : ''}`;
                }
                return `<li ${attrs.join(' ')}>${inner}</li>`;
            }).filter(Boolean);
            if (!lis.length) return;

            const bodyHtml = `<ul class="chat-response-sources-list">${lis.join('')}</ul>`;
            let details = container.querySelector('.chat-response-sources');
            if (!details) {
                details = document.createElement('div');
                details.className = 'chat-response-sources';
                details.innerHTML = `<div class="chat-response-sources-body">${bodyHtml}</div>`;
                container.appendChild(details);
                return;
            }
            let body = details.querySelector('.chat-response-sources-body');
            if (!body) {
                body = document.createElement('div');
                body.className = 'chat-response-sources-body mt-2 text-sm text-gray-600';
                details.appendChild(body);
            }
            body.innerHTML = bodyHtml;
        } catch (_) { /* never break rendering */ }
    },

    /**
     * Prefer structured rows emitted by the server (`data-source-title`, etc.).
     */
    _parseStructuredSourceRows(bodyEl) {
        const items = [];
        if (!bodyEl || typeof bodyEl.querySelectorAll !== 'function') return items;
        const rows = bodyEl.querySelectorAll('[data-source-title]');
        if (!rows.length) return items;
        rows.forEach((row) => {
            const title = this._squashPlain(row.getAttribute('data-source-title') || '');
            if (!title) return;
            const detail = this._squashPlain(row.getAttribute('data-source-detail') || '');
            const urlRaw = (row.getAttribute('data-source-url') || '').trim();
            const pageRaw = (row.getAttribute('data-source-page') || '').trim();
            let url = null;
            if (urlRaw) {
                url = this._safeSameOriginUrl(urlRaw) || (/^https?:\/\//i.test(urlRaw) ? urlRaw : null);
            }
            let page = null;
            if (pageRaw) {
                const n = Number(pageRaw);
                page = Number.isFinite(n) ? String(Math.trunc(n)) : pageRaw;
            }
            items.push({
                title,
                page,
                url,
                excerpt: detail || null,
            });
        });
        return items;
    },

    /**
     * Older replies stored a Sources body as prose or <br> lines with no data-* attrs.
     * Each line becomes one chip item so the disclosure style cannot remain.
     */
    _plainSourceItemsFromBody(bodyEl) {
        const items = [];
        const notes = [];
        if (!bodyEl) return { items, notes };
        const push = (plain, url) => {
            const title = this._squashPlain(plain).replace(/^(?:[-*•]|\d{1,3}[.)])\s+/, '').trim();
            if (!title || /^sources:?$/i.test(title)) return;
            if (this._isAnswerVerificationCaveatText(title)) {
                notes.push(title.replace(/^>?\s*/, ''));
                return;
            }
            let safeUrl = null;
            if (url) {
                safeUrl = this._safeSameOriginUrl(url) || (/^https?:\/\//i.test(url) ? url : null);
            }
            items.push({ title, page: null, url: safeUrl, excerpt: null });
        };
        const lis = bodyEl.querySelectorAll('li');
        if (lis.length) {
            lis.forEach((li) => {
                if (li.hasAttribute('data-source-title')) return;
                const link = li.querySelector('a[href]');
                push(li.textContent, link ? link.getAttribute('href') : null);
            });
            return { items, notes };
        }
        const parts = (bodyEl.innerHTML || '').split(/<br\s*\/?>/i);
        parts.forEach((part) => {
            const tmp = document.createElement('div');
            tmp.innerHTML = part;
            const link = tmp.querySelector('a[href]');
            push(tmp.textContent, link ? link.getAttribute('href') : null);
        });
        return { items, notes };
    },

    /**
     * Parse .chat-response-sources-body. Prefer data-source-* rows, then any remaining text.
     * Verification caveats stay as notes on the chip modal.
     */
    _parseChatResponseSources(detailsEl) {
        const items = [];
        const notes = [];
        if (!detailsEl) return { items, notes };
        const bodyEl = detailsEl.querySelector('.chat-response-sources-body') || detailsEl;
        if (!bodyEl) return { items, notes };

        const structured = this._parseStructuredSourceRows(bodyEl);
        if (structured.length) {
            bodyEl.querySelectorAll('li, p').forEach((el) => {
                if (el.hasAttribute('data-source-title')) return;
                const plain = this._squashPlain(el.textContent || '');
                if (this._isAnswerVerificationCaveatText(plain)) {
                    notes.push(plain.replace(/^>?\s*/, ''));
                }
            });
            return { items: structured, notes };
        }

        return this._plainSourceItemsFromBody(bodyEl);
    },

    _closeSourcesModal() {
        const existing = document.getElementById('chatSourcesModalOverlay');
        if (existing) existing.remove();
        if (this._sourcesModalKeyHandler) {
            document.removeEventListener('keydown', this._sourcesModalKeyHandler);
            this._sourcesModalKeyHandler = null;
        }
    },

    _openSourcesModal(parsed) {
        this._closeSourcesModal();
        const items = (parsed && parsed.items) || [];
        const notes = (parsed && parsed.notes) || [];
        const titleText = this._uiString('responseSources') || 'Sources';

        const overlay = document.createElement('div');
        overlay.id = 'chatSourcesModalOverlay';
        overlay.className = 'chat-sources-modal-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', titleText);

        const panel = document.createElement('div');
        panel.className = 'chat-sources-modal-panel';

        const header = document.createElement('div');
        header.className = 'chat-sources-modal-header';
        const heading = document.createElement('h2');
        heading.className = 'chat-sources-modal-title';
        heading.textContent = titleText;
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'chat-sources-modal-close';
        closeBtn.setAttribute('aria-label', this._uiString('close') || 'Close');
        closeBtn.innerHTML = '<i class="fas fa-times" aria-hidden="true"></i>';
        closeBtn.addEventListener('click', () => this._closeSourcesModal());
        header.append(heading, closeBtn);

        const list = document.createElement('div');
        list.className = 'chat-sources-modal-list';

        items.forEach((item, idx) => {
            const row = document.createElement(item.url ? 'a' : 'div');
            row.className = 'chat-sources-modal-item' + (item.url ? ' is-link' : '');
            if (item.url) {
                row.href = item.url;
                row.target = '_blank';
                row.rel = 'noopener';
            }
            const indexEl = document.createElement('span');
            indexEl.className = 'chat-sources-modal-index';
            indexEl.textContent = String(idx + 1);
            const body = document.createElement('div');
            body.className = 'chat-sources-modal-item-body';
            const titleEl = document.createElement('div');
            titleEl.className = 'chat-sources-modal-item-title';
            titleEl.textContent = item.title;
            body.appendChild(titleEl);
            if (item.page) {
                const pageEl = document.createElement('span');
                pageEl.className = 'chat-sources-modal-page';
                pageEl.textContent = 'p. ' + item.page;
                body.appendChild(pageEl);
            }
            if (item.excerpt) {
                const excerptEl = document.createElement('div');
                excerptEl.className = 'chat-sources-modal-excerpt';
                excerptEl.textContent = item.excerpt;
                body.appendChild(excerptEl);
            }
            row.appendChild(indexEl);
            row.appendChild(body);
            if (item.url) {
                const openIcon = document.createElement('i');
                openIcon.className = 'fas fa-external-link-alt chat-sources-modal-open-icon';
                openIcon.setAttribute('aria-hidden', 'true');
                row.appendChild(openIcon);
            }
            list.appendChild(row);
        });

        notes.forEach((note) => {
            const noteEl = document.createElement('div');
            noteEl.className = 'chat-sources-modal-note';
            noteEl.innerHTML = '<i class="fas fa-info-circle" aria-hidden="true"></i>';
            const noteText = document.createElement('span');
            noteText.textContent = note;
            noteEl.appendChild(noteText);
            list.appendChild(noteEl);
        });

        if (!items.length && !notes.length) {
            const empty = document.createElement('div');
            empty.className = 'chat-sources-modal-empty';
            empty.textContent = this._uiString('noSourcesListed') || 'No sources listed.';
            list.appendChild(empty);
        }

        panel.append(header, list);
        overlay.appendChild(panel);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) this._closeSourcesModal();
        });
        this._sourcesModalKeyHandler = (e) => {
            if (e.key === 'Escape') this._closeSourcesModal();
        };
        document.addEventListener('keydown', this._sourcesModalKeyHandler);
        document.body.appendChild(overlay);
        try { closeBtn.focus(); } catch (_) { /* ignore */ }
    },

    _sourcesParsedToCopyText(parsed) {
        const items = (parsed && parsed.items) || [];
        const notes = (parsed && parsed.notes) || [];
        const lines = [];
        if (items.length || notes.length) {
            lines.push((this._uiString('responseSources') || 'Sources') + ':');
        }
        items.forEach((item, idx) => {
            let line = `${idx + 1}. ${item.title || ''}`;
            if (item.page) line += ` (p. ${item.page})`;
            if (item.url) line += ` — ${item.url}`;
            if (item.excerpt) line += `\n   ${item.excerpt}`;
            lines.push(line);
        });
        notes.forEach((note) => lines.push(String(note || '')));
        return lines.join('\n').trim();
    },

    _buildSourcesChip(parsed) {
        const items = (parsed && parsed.items) || [];
        const count = items.length;
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chat-response-sources-chip';
        chip.setAttribute('aria-label', (this._uiString('responseSources') || 'Sources') + (count ? ' (' + count + ')' : ''));
        // Keep structured sources available for copy-to-clipboard after the details block is replaced.
        chip.__humdbSourcesParsed = parsed;
        chip.setAttribute('data-sources-copy', this._sourcesParsedToCopyText(parsed));

        const bookIcon = document.createElement('i');
        bookIcon.className = 'fas fa-book-open chat-response-sources-chip-icon';
        bookIcon.setAttribute('aria-hidden', 'true');

        const label = document.createElement('span');
        label.className = 'chat-response-sources-chip-label';
        label.textContent = this._uiString('responseSources') || 'Sources';

        chip.append(bookIcon, label);
        if (count > 0) {
            const badge = document.createElement('span');
            badge.className = 'chat-response-sources-chip-count';
            badge.textContent = String(count);
            chip.appendChild(badge);
        }
        const chevron = document.createElement('i');
        chevron.className = 'fas fa-chevron-right chat-response-sources-chip-chevron';
        chevron.setAttribute('aria-hidden', 'true');
        chip.appendChild(chevron);

        chip.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this._openSourcesModal(parsed);
        });
        return chip;
    },

    /**
     * Place the Sources chip on the action row, after the copy/like icons,
     * with a vertical divider between those icons and the chip.
     */
    _relocateSourcesChipIfNeeded(wrapperOrContainer) {
        try {
            const wrapper = wrapperOrContainer?.closest
                ? (wrapperOrContainer.classList?.contains('chat-message-wrapper')
                    ? wrapperOrContainer
                    : wrapperOrContainer.closest('.chat-message-wrapper'))
                : null;
            if (!wrapper) return;
            const actionBar = wrapper.querySelector('.chat-message-actions');
            if (!actionBar) return;

            const chip = wrapper.querySelector('.chat-response-sources-chip');
            if (!chip) return;

            let sep = actionBar.querySelector('.chat-message-actions-sep');
            if (!sep) {
                sep = document.createElement('span');
                sep.className = 'chat-message-actions-sep';
                sep.setAttribute('aria-hidden', 'true');
            }
            const holder = chip.closest('.chat-response-sources--chip');
            actionBar.appendChild(sep);
            actionBar.appendChild(chip);
            if (holder && holder !== actionBar && !holder.querySelector('.chat-response-sources-chip')) {
                holder.remove();
            }
        } catch (_) { /* never break rendering */ }
    },

    /**
     * Render Sources only as a chip that opens the modal. Any leftover
     * disclosure or prose block is replaced or removed.
     */
    _formatChatResponseSources(container) {
        if (!container || typeof container.querySelector !== 'function') return;
        this._normalizeSourcesSection(container);
        const sourcesBlocks = container.querySelectorAll('.chat-response-sources');
        sourcesBlocks.forEach((detailsEl) => {
            if (detailsEl.getAttribute('data-sources-formatted') === '1') return;
            if (detailsEl.querySelector('.chat-response-sources-chip')) return;
            const parsed = this._parseChatResponseSources(detailsEl);
            if (!parsed.items.length && !parsed.notes.length) {
                detailsEl.remove();
                return;
            }
            const chip = this._buildSourcesChip(parsed);
            const holder = document.createElement('div');
            holder.className = 'chat-response-sources chat-response-sources--chip';
            holder.setAttribute('data-sources-formatted', '1');
            holder.appendChild(chip);
            if (detailsEl.parentNode) detailsEl.parentNode.insertBefore(holder, detailsEl);
            detailsEl.remove();
        });
        this._relocateSourcesChipIfNeeded(container);
    },

    _enhanceIndicatorActionLinks(root) {
        /** Promote indicator view/edit links to styled CTA buttons (new tab). */
        try {
            if (!root || typeof root.querySelectorAll !== 'function') return;
            const re = /^\/admin\/indicator_bank\/(?:view|edit)\/\d+/;
            root.querySelectorAll('a[href]').forEach((link) => {
                if (link.closest('.chat-response-sources')) return;
                const rawHref = link.getAttribute('href') || '';
                const safe = this._safeSameOriginUrl(rawHref.split('#')[0]);
                if (!safe || !re.test(safe)) return;
                link.classList.add('chatbot-show-me');
                link.classList.remove('underline', 'text-blue-600', 'hover:text-blue-800');
                link.setAttribute('href', safe);
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener');
            });
        } catch (_) { /* never break rendering */ }
    },

    _augmentOnboardingActions(root) {
        /**
         * Add "Take a quick tour" CTA links for workflow-enabled flows.
         *
         * Behavior:
         * 1) If the message already contains a chatbot-tour link, upgrade it to button styling.
         * 2) Else infer a tour link from workflow/page hints and append a CTA button link.
         *
         * Returns the CTA element when a new one is created, so it can be positioned in the wrapper.
         */
        if (this._fbAiConfig) return null;
        try {
            if (!root || typeof root.querySelector !== 'function') return null;
            const ctaLabel = this._uiString('takeQuickTour') || 'Take a quick tour';

            // If AI already included a tour deep-link, just style it as CTA.
            const existingTourLink = root.querySelector('a[href*="chatbot-tour="]:not(.chatbot-show-me)');
            if (existingTourLink && !existingTourLink.closest('.chat-response-sources')) {
                const safeHref = this._safeSameOriginUrl(existingTourLink.getAttribute('href') || '');
                if (safeHref) {
                    existingTourLink.setAttribute('href', safeHref);
                    existingTourLink.classList.add('chatbot-show-me');
                    if (!(existingTourLink.textContent || '').trim()) {
                        existingTourLink.textContent = ctaLabel;
                    }
                }
                return null;
            }

            if (root.querySelector('a.chatbot-show-me')) return null; // already present

            const tourHref = this._inferWorkflowTourHref(root);
            if (!tourHref) return null;

            const showMe = document.createElement('a');
            showMe.className = 'chatbot-show-me';
            showMe.setAttribute('href', tourHref);
            showMe.textContent = ctaLabel;
            return showMe;
        } catch (error) {
            // Never break message rendering
            console.warn('Failed to augment onboarding actions:', error);
        }
        return null;
    },

    _inferWorkflowTourHref(root) {
        /**
         * Best-effort derivation of a workflow tour deep-link from chatbot message content.
         */
        try {
            if (!root || typeof root.querySelector !== 'function') return null;

            // 1) Explicit chatbot-tour links already present in message.
            const explicitTourLink = root.querySelector('a[href*="chatbot-tour="]');
            if (explicitTourLink && !explicitTourLink.closest('.chat-response-sources')) {
                const safe = this._safeSameOriginUrl(explicitTourLink.getAttribute('href') || '');
                if (safe) return safe;
            }

            // 2) Explicit workflow trigger button/link with workflow id.
            const workflowTrigger = root.querySelector('.chatbot-tour-trigger[data-workflow]');
            if (workflowTrigger && !workflowTrigger.closest('.chat-response-sources')) {
                const workflowId = String(workflowTrigger.getAttribute('data-workflow') || '').trim();
                if (!workflowId) return null;
                const rawHref = String(workflowTrigger.getAttribute('href') || '').trim();
                const targetPath = rawHref ? rawHref.split('#')[0] : window.location.pathname;
                const composed = `${targetPath}#chatbot-tour=${encodeURIComponent(workflowId)}`;
                return this._safeSameOriginUrl(composed);
            }

            // 3) Fallback: infer workflow from known admin pages linked in the response.
            const fallbackByPath = {
                '/admin/users': 'add-user',
                '/admin/assignments': 'create-assignment',
                '/admin/templates': 'create-template',
            };
            const links = Array.from(root.querySelectorAll('a[href]'));
            for (const link of links) {
                if (link.closest('.chat-response-sources')) continue;
                const safeHref = this._safeSameOriginUrl(link.getAttribute('href') || '');
                if (!safeHref) continue;
                const parsed = new URL(safeHref, window.location.origin);
                const path = String(parsed.pathname || '').replace(/\/+$/, '') || '/';
                const workflowId = fallbackByPath[path];
                if (!workflowId) continue;
                return `${path}${parsed.search || ''}#chatbot-tour=${encodeURIComponent(workflowId)}`;
            }
            // 4) Plain-text fallback: AI may mention a path as text rather than a hyperlink.
            const bodyText = (root.textContent || root.innerText || '');
            for (const [path, workflowId] of Object.entries(fallbackByPath)) {
                if (bodyText.includes(path)) {
                    return `${path}#chatbot-tour=${encodeURIComponent(workflowId)}`;
                }
            }
        } catch (error) {
            console.debug('Failed to infer workflow tour href:', error);
        }
        return null;
    }

};
