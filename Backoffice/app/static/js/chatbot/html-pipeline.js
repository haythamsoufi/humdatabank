/**
 * Chatbot HtmlPipeline module
 * @module chatbot/html-pipeline
 */

export const HtmlPipelineMixin = {
    escapeHtml(text) {
        if (typeof text !== 'string') return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
            .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n, 10)))
            .replace(/&#x([0-9a-fA-F]+);/g, (_, n) => String.fromCharCode(parseInt(n, 16)));
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
                this._warn('Markdown table reject payload JSON:', JSON.stringify(rejectPayload));
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
     * If text contains "## Sources" (markdown), extract that section and replace it with
     * the same <details class="chat-response-sources"> structure the backend uses.
     * Ensures sources are always formatted whether response is HTML (from stream) or markdown (e.g. from DB on refresh).
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
        const sourcesRegex = new RegExp('(?m)^((?:#{2,3}\\s*)?Sources\\s*:?\\s*)\\s*$(.+?)' + stopAt, 'is');
        const sourcesMatch = text.match(sourcesRegex);
        if (!sourcesMatch) return text;
        const sourcesBlockRaw = sourcesMatch[2].trim();
        const mainPart = text.slice(0, sourcesMatch.index).trim();
        const placeholder = '__HUMDATABANK_AI_SOURCES__';
        let combined = mainPart + '\n\n' + placeholder;
        // Escape and format sources block: newlines -> <br>, markdown links -> <a>
        let sourcesEsc = this.escapeHtml(sourcesBlockRaw);
        sourcesEsc = sourcesEsc.replace(/\n+/g, '<br>').replace(/(<br>){2,}/g, '<br><br>');
        sourcesEsc = sourcesEsc.replace(/\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g, (_, label, href) => {
            const safe = this._safeSameOriginUrl(href);
            if (!safe) return this.escapeHtml(label || '');
            return '<a href="' + this.escapeHtml(safe) + '" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">' + this.escapeHtml(label || '') + '</a>';
        });
        const sourcesHtml = (
            '<details class="chat-response-sources mt-2 border border-gray-200 rounded p-2 bg-gray-50">' +
            '<summary class="cursor-pointer font-medium text-gray-700">Sources</summary>' +
            '<div class="chat-response-sources-body mt-2 text-sm text-gray-600">' + sourcesEsc + '</div></details>'
        );
        return combined.replace(placeholder, sourcesHtml);
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
                if (
                    v.includes('javascript:') ||
                    v.includes('data:') ||
                    v.includes('vbscript:') ||
                    v.includes('file:') ||
                    v.includes('about:')
                ) {
                    element.removeAttribute(attr.name);
                    continue;
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
            let list = heading.nextElementSibling;
            if (!list || !/^UL|OL$/i.test(list.tagName)) return;
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
            let list = p.nextElementSibling;
            if (!list || !/^UL|OL$/i.test(list.tagName)) return;
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

    _formatChatResponseSources(container) {
        if (!container || typeof container.querySelector !== 'function') return;
        this._normalizeSourcesSection(container);
        const isAnswerVerificationCaveatText = (plain) => {
            const t = (plain || '')
                .toLowerCase()
                .replace(/\s+/g, ' ')
                .trim();
            if (!t) {
                return false;
            }
            if (t.includes('could not be verified against the available sources')) {
                return true;
            }
            if (t.startsWith('note:') && t.includes('could not be verified')) {
                return true;
            }
            if (t.startsWith('> note:') && t.includes('could not be verified')) {
                return true;
            }
            return false;
        };
        const countProbe = document.createElement('div');
        const sourcesBlocks = container.querySelectorAll('.chat-response-sources');
        sourcesBlocks.forEach((detailsEl) => {
            const bodyEl = detailsEl.querySelector('.chat-response-sources-body');
            if (!bodyEl) return;
            let html = bodyEl.innerHTML.trim();
            if (!html) return;
            let segments = html.split(/\s*<br\s*\/?>\s*/i).map((s) => s.trim()).filter(Boolean);
            if (segments.length <= 1 && bodyEl.querySelector('ul li, ol li')) {
                const items = bodyEl.querySelectorAll('ul li, ol li');
                const fromList = Array.from(items).map((li) => (li.innerHTML || li.textContent || '').trim()).filter(Boolean);
                if (fromList.length > segments.length) segments = fromList;
            }
            if (!segments.length) return;
            const sanitizeSegmentHtml = (html) => (window.sanitizeHtml || ((h) => h))(html);
            let sourceCountForLabel = 0;
            for (const segment of segments) {
                countProbe.innerHTML = sanitizeSegmentHtml(segment);
                const p = (countProbe.textContent || '').replace(/\s+/g, ' ').trim();
                if (p && !isAnswerVerificationCaveatText(p)) {
                    sourceCountForLabel += 1;
                }
            }
            let summaryEl = detailsEl.querySelector('summary');
            if (!summaryEl) {
                summaryEl = document.createElement('summary');
                detailsEl.insertBefore(summaryEl, bodyEl);
            }
            summaryEl.textContent = 'Sources (' + sourceCountForLabel + ')';
            const resolveSourceIcon = (segmentHtml, plainText) => {
                const probe = document.createElement('div');
                probe.innerHTML = sanitizeSegmentHtml(segmentHtml);
                const anchor = probe.querySelector('a[href]');
                const href = (anchor?.getAttribute('href') || '').trim();
                const label = ((anchor?.textContent || '') + ' ' + plainText).toLowerCase();
                const hrefLower = href.toLowerCase();
                const normalizedHref = hrefLower.split('#')[0];
                const hrefNoQuery = normalizedHref.split('?')[0];
                const pdfHints = hrefLower + ' ' + label;
                const hasPageCitation = /\bpage\s+\d+\b/i.test(label);
                const isInternalUploadedDoc =
                    /\/ai\/documents(?:\/|$)/i.test(hrefNoQuery) ||
                    /\/uploads\/ai_documents(?:\/|$)/i.test(hrefNoQuery) ||
                    /\/documents\/view(?:\/|$)/i.test(hrefNoQuery);

                const isLikelyLink = /^https?:\/\//i.test(href) || /\bhttps?:\/\//i.test(plainText);
                const isDataRecord = /\b(country record|record:|databank|database|kpi|indicator)\b/i.test(label);
                const isPdf =
                    /\.pdf(\b|$)/i.test(hrefNoQuery) ||
                    /(?:^|[?&])(format|mime|type|content_type)=application\/pdf(?:&|$)/i.test(hrefLower) ||
                    /(?:^|[?&])(format|mime|type)=pdf(?:&|$)/i.test(hrefLower) ||
                    /\/pdf(?:\/|$)/i.test(hrefNoQuery) ||
                    /\bapplication\/pdf\b/i.test(pdfHints) ||
                    (hasPageCitation && !isDataRecord) ||
                    isInternalUploadedDoc ||
                    /\bpdf\b/i.test(label);
                if (isPdf) return { icon: 'fa-file-pdf', iconStyle: 'fas', type: 'pdf', title: 'PDF source' };

                if (isDataRecord && !href) return { icon: 'fa-database', type: 'data', title: 'Data source' };

                const isWord = /\.(doc|docx|odt|rtf)$/i.test(normalizedHref) || /\b(doc|docx|word)\b/i.test(label);
                if (isWord) return { icon: 'fa-file-word', type: 'word', title: 'Document source' };

                const isSheet = /\.(xls|xlsx|csv|ods)$/i.test(normalizedHref) || /\b(xls|xlsx|csv|excel|spreadsheet)\b/i.test(label);
                if (isSheet) return { icon: 'fa-file-excel', type: 'sheet', title: 'Spreadsheet source' };

                const isSlides = /\.(ppt|pptx|odp)$/i.test(normalizedHref) || /\b(ppt|pptx|powerpoint|slides)\b/i.test(label);
                if (isSlides) return { icon: 'fa-file-powerpoint', type: 'slides', title: 'Presentation source' };

                const isImage = /\.(png|jpe?g|gif|webp|svg|bmp|tiff?)$/i.test(normalizedHref) || /\b(image|photo|png|jpg|jpeg|gif|webp|svg)\b/i.test(label);
                if (isImage) return { icon: 'fa-file-image', type: 'image', title: 'Image source' };

                if (isLikelyLink) return { icon: 'fa-link', type: 'link', title: 'Web source' };
                return { icon: 'fa-file-lines', iconStyle: 'fas', type: 'file', title: 'Source file' };
            };
            const self = this;
            const linkifySegment = (seg) => {
                const hasLink = /<a\s[^>]*href\s*=/i.test(seg);
                const hasMdLink = /\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/.test(seg);
                if (hasLink) {
                    return seg;
                }
                const out = seg.replace(/\[([^\]]*)\]\((https?:\/\/[^)\s]+|\/[^)\s]*)\)/g, (_, label, href) => {
                    const safe = self._safeSameOriginUrl(href);
                    if (!safe) return self.escapeHtml(label || '');
                    return '<a href="' + self.escapeHtml(safe) + '" class="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener">' + self.escapeHtml(label || '') + '</a>';
                });
                return out;
            };
            const fragment = document.createDocumentFragment();
            const tempDiv = document.createElement('div');
            segments.forEach((segment) => {
                segment = linkifySegment(segment);
                tempDiv.innerHTML = sanitizeSegmentHtml(segment);
                const plainText = (tempDiv.textContent || '').trim();
                const lineEl = document.createElement('div');
                lineEl.className = 'chat-source-line';
                const iconInfo = resolveSourceIcon(segment, plainText);
                const iconSpan = document.createElement('span');
                iconSpan.className = 'chat-source-line-icon chat-source-line-icon-' + iconInfo.type;
                iconSpan.setAttribute('aria-hidden', 'true');
                iconSpan.setAttribute('title', iconInfo.title);
                const iconStyleClass = iconInfo.iconStyle || 'fas';
                iconSpan.innerHTML = '<i class="' + iconStyleClass + ' ' + iconInfo.icon + '" aria-hidden="true"></i>';
                const previewSpan = document.createElement('span');
                previewSpan.className = 'chat-source-line-preview';
                previewSpan.textContent = plainText || '\u00a0';
                const toggleSpan = document.createElement('span');
                toggleSpan.className = 'chat-source-line-toggle';
                toggleSpan.setAttribute('aria-hidden', 'true');
                toggleSpan.textContent = '\u203a';
                const fullSpan = document.createElement('span');
                fullSpan.className = 'chat-source-line-full';
                fullSpan.innerHTML = sanitizeSegmentHtml(segment);
                lineEl.appendChild(iconSpan);
                lineEl.appendChild(previewSpan);
                lineEl.appendChild(toggleSpan);
                lineEl.appendChild(fullSpan);
                lineEl.addEventListener('click', (e) => {
                    const link = e.target.closest('a');
                    const insideFull = e.target.closest('.chat-source-line-full');
                    const isLinkClick = !!link;
                    const isInsideExpandedContent = !!insideFull;
                    const shouldNotToggle = isLinkClick || isInsideExpandedContent;
                    if (shouldNotToggle) {
                        if (isLinkClick) e.stopPropagation();
                        return;
                    }
                    lineEl.classList.toggle('expanded');
                    lineEl.setAttribute('aria-expanded', lineEl.classList.contains('expanded'));
                });
                lineEl.setAttribute('role', 'button');
                lineEl.setAttribute('tabIndex', '0');
                lineEl.setAttribute('aria-expanded', 'false');
                lineEl.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        lineEl.classList.toggle('expanded');
                        lineEl.setAttribute('aria-expanded', lineEl.classList.contains('expanded'));
                    }
                });
                fragment.appendChild(lineEl);
            });
            bodyEl.innerHTML = '';
            bodyEl.appendChild(fragment);

            // Prevent link clicks from bubbling to the row (which would toggle expand/collapse)
            if (!bodyEl.hasAttribute('data-sources-link-handler')) {
                bodyEl.setAttribute('data-sources-link-handler', '1');
                bodyEl.addEventListener('click', (e) => {
                    const a = e.target.closest('a');
                    const inSourceLine = a && a.closest('.chat-source-line');
                    if (a && inSourceLine) {
                        e.stopPropagation();
                    }
                }, true);
            }

            const sourceLines = bodyEl.querySelectorAll('.chat-source-line');
            const DEFAULT_VISIBLE_SOURCES = 5;
            if (sourceLines.length > DEFAULT_VISIBLE_SOURCES) {
                for (let i = DEFAULT_VISIBLE_SOURCES; i < sourceLines.length; i++) {
                    sourceLines[i].classList.add('chat-source-line-hidden');
                }
                const expandRow = document.createElement('div');
                expandRow.className = 'chat-sources-expand-row';
                expandRow.setAttribute('role', 'button');
                expandRow.setAttribute('tabIndex', '0');
                expandRow.setAttribute('aria-label', 'Show more sources');
                expandRow.innerHTML = '<span class="chat-sources-expand-label">Show ' + (sourceLines.length - DEFAULT_VISIBLE_SOURCES) + ' more sources</span> <i class="fas fa-chevron-down chat-sources-expand-icon" aria-hidden="true"></i>';
                expandRow.addEventListener('click', () => {
                    bodyEl.querySelectorAll('.chat-source-line-hidden').forEach((el) => el.classList.remove('chat-source-line-hidden'));
                    expandRow.remove();
                    detailsEl.classList.add('chat-response-sources-expanded');
                });
                expandRow.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        expandRow.click();
                    }
                });
                bodyEl.appendChild(expandRow);
            }
        });
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
