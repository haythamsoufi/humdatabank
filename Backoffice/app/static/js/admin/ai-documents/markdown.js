/**
 * Small markdown renderer for Ask AI answers. HTML is escaped before inline
 * markup is applied, then sanitizeHtml strips anything the renderer did not emit.
 */

import { escapeHtml, sanitizeUrl } from './shared.js';

export function renderMarkdown(text) {
    if (!text) return '';

    const lines = text.split('\n');
    const result = [];
    let inCodeBlock = false;
    let codeBlockContent = [];
    const listStack = [];

    function listHtml(list) {
        const tag = list.type === 'ol' ? 'ol' : 'ul';
        return '<' + tag + '>' + list.items.join('') + '</' + tag + '>';
    }

    function nestIntoLastItem(list, html) {
        const lastIdx = list.items.length - 1;
        if (lastIdx >= 0) {
            list.items[lastIdx] = list.items[lastIdx].replace('</li>', html + '</li>');
        }
    }

    function flushList() {
        if (listStack.length === 0) return;
        let current = null;
        while (listStack.length > 0) {
            const list = listStack.pop();
            if (current) nestIntoLastItem(list, current);
            current = listHtml(list);
        }
        if (current) result.push(current);
    }

    function addListItem(content, indent, type) {
        while (listStack.length > 0 && listStack[listStack.length - 1].indent >= indent) {
            const popped = listStack.pop();
            const html = listHtml(popped);
            if (listStack.length > 0) nestIntoLastItem(listStack[listStack.length - 1], html);
            else result.push(html);
        }

        const item = '<li>' + processInline(content) + '</li>';
        if (listStack.length > 0 && listStack[listStack.length - 1].indent === indent) {
            listStack[listStack.length - 1].items.push(item);
        } else {
            listStack.push({ type: type, items: [item], indent: indent });
        }
    }

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const trimmed = line.trim();

        if (trimmed.startsWith('```')) {
            if (inCodeBlock) {
                result.push('<pre><code>' + escapeHtml(codeBlockContent.join('\n')) + '</code></pre>');
                codeBlockContent = [];
                inCodeBlock = false;
            } else {
                flushList();
                inCodeBlock = true;
            }
            continue;
        }

        if (inCodeBlock) {
            codeBlockContent.push(line);
            continue;
        }

        if (trimmed.startsWith('### ')) {
            flushList();
            result.push('<h3>' + processInline(trimmed.substring(4)) + '</h3>');
            continue;
        }
        if (trimmed.startsWith('## ')) {
            flushList();
            result.push('<h2>' + processInline(trimmed.substring(3)) + '</h2>');
            continue;
        }
        if (trimmed.startsWith('# ')) {
            flushList();
            result.push('<h1>' + processInline(trimmed.substring(2)) + '</h1>');
            continue;
        }

        if (trimmed === '---' || trimmed === '***') {
            flushList();
            result.push('<hr>');
            continue;
        }

        if (trimmed.startsWith('> ')) {
            flushList();
            result.push('<blockquote>' + processInline(trimmed.substring(2)) + '</blockquote>');
            continue;
        }

        const ulMatch = line.match(/^(\s*)([*\-+]\s+)(.+)$/);
        if (ulMatch) {
            addListItem(ulMatch[3], ulMatch[1].length, 'ul');
            continue;
        }

        const olMatch = line.match(/^(\s*)(\d+[.)]\s+)(.+)$/);
        if (olMatch) {
            addListItem(olMatch[3], olMatch[1].length, 'ol');
            continue;
        }

        if (trimmed === '') {
            flushList();
            if (result.length > 0 && !result[result.length - 1].endsWith('</p>') &&
                !result[result.length - 1].endsWith('</ul>') &&
                !result[result.length - 1].endsWith('</ol>')) {
                result.push('<br>');
            }
            continue;
        }

        flushList();
        result.push('<p>' + processInline(trimmed) + '</p>');
    }

    flushList();
    if (inCodeBlock && codeBlockContent.length > 0) {
        result.push('<pre><code>' + escapeHtml(codeBlockContent.join('\n')) + '</code></pre>');
    }

    return result.join('');

    function processInline(value) {
        let html = escapeHtml(value);
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function (match, linkText, url) {
            const safeHref = escapeHtml(sanitizeUrl(url));
            return '<a href="' + safeHref + '" target="_blank" rel="noopener noreferrer">' + linkText + '</a>';
        });
        html = html.replace(/\[(\d{1,3})\](?!\()/g, '<span class="citation">[$1]</span>');
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        html = html.replace(/\*\*([^*]+?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__([^_]+?)__/g, '<strong>$1</strong>');
        html = html.replace(/(^|[^*])\*([^*\n]+?)\*([^*]|$)/g, '$1<em>$2</em>$3');
        html = html.replace(/(^|[^_])_([^_\n]+?)_([^_]|$)/g, '$1<em>$2</em>$3');
        return html;
    }
}

export function sanitizeHtml(html) {
    if (!html) return '';
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const allowedTags = new Set([
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
        'a', 'span', 'div', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'hr', 'sup', 'sub', 'mark',
    ]);
    const allowedAttrs = {
        a: ['href', 'target', 'rel', 'class'],
        span: ['class'],
        div: ['class'],
        code: ['class'],
        pre: ['class'],
        '*': ['class'],
    };
    const dangerousProtocols = /^(javascript|vbscript|data):/i;

    function sanitizeNode(node) {
        if (node.nodeType === Node.TEXT_NODE) return;
        if (node.nodeType !== Node.ELEMENT_NODE) {
            node.remove();
            return;
        }
        const tagName = node.tagName.toLowerCase();
        if (!allowedTags.has(tagName)) {
            node.replaceWith(document.createTextNode(node.textContent));
            return;
        }
        Array.from(node.attributes).forEach(function (attr) {
            const attrName = attr.name.toLowerCase();
            const tagAllowed = allowedAttrs[tagName] || [];
            const globalAllowed = allowedAttrs['*'] || [];
            if (attrName.startsWith('on') || (!tagAllowed.includes(attrName) && !globalAllowed.includes(attrName))) {
                node.removeAttribute(attr.name);
                return;
            }
            if (attrName === 'href') {
                const hrefVal = (attr.value || '').replace(/[\s\x00-\x1f]/g, '');
                if (dangerousProtocols.test(hrefVal)) node.removeAttribute('href');
            }
        });
        if (tagName === 'a' && node.getAttribute('target') === '_blank' && !node.getAttribute('rel')) {
            node.setAttribute('rel', 'noopener noreferrer');
        }
        Array.from(node.childNodes).forEach(sanitizeNode);
    }

    Array.from(doc.body.childNodes).forEach(sanitizeNode);
    return doc.body.innerHTML;
}
