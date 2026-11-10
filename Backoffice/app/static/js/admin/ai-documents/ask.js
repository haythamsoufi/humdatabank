/**
 * Ask AI panel. A WebSocket application error is shown as-is.
 * Transport failures still fall back to HTTP.
 */

import { renderMarkdown, sanitizeHtml } from './markdown.js';
import { cfg, escapeHtml, getFileTypeIcon } from './shared.js';

export class AnswerRequestError extends Error {
    constructor(message, options) {
        super(message);
        this.application = !!(options && options.application);
    }
}

function classifyModel(modelName) {
    const m = String(modelName || '').trim();
    if (!m) return { kind: 'unknown', label: null };
    const local = {
        table_records: 'Local (table_records)',
        upr_visual: 'Local (upr_visual)',
        metric_blocks: 'Local (metric_blocks)',
        people_reached_blocks: 'Local (people_reached_blocks)',
        people_to_be_reached_blocks: 'Local (people_to_be_reached_blocks)',
        participating_national_societies_blocks: 'Local (participating_national_societies_blocks)',
        financial_overview_blocks: 'Local (financial_overview_blocks)',
        none: 'Local (no model used)',
    };
    if (local[m]) return { kind: 'local', label: local[m] };
    if (m === 'error') return { kind: 'error', label: 'Error (backend)' };
    return { kind: 'model', label: m };
}

function setAnswerStatus(aiAnswerStatus, { transport, model, issues } = {}) {
    if (!aiAnswerStatus) return;
    const parts = [];
    if (transport) parts.push('<i class="fas fa-exchange-alt mr-1"></i>' + escapeHtml(transport));
    if (model) parts.push('<i class="fas fa-brain mr-1"></i>' + escapeHtml(model));
    if (Array.isArray(issues) && issues.length) {
        parts.push('<i class="fas fa-exclamation-triangle mr-1"></i>' + issues.map(escapeHtml).join(' • '));
    }
    const html = parts.join(' <span class="mx-2 text-gray-300">|</span> ');
    if (html) {
        aiAnswerStatus.innerHTML = html;
        aiAnswerStatus.classList.remove('hidden');
    } else {
        aiAnswerStatus.innerHTML = '';
        aiAnswerStatus.classList.add('hidden');
    }
}

function ensureAnswerShown(aiAnswerOutput, answerText, answerHtml) {
    if (!aiAnswerOutput) return;
    const answerSection = document.getElementById('aiAnswerSection');
    if (answerSection && (answerText || answerHtml)) answerSection.classList.remove('hidden');
    if (answerHtml) {
        aiAnswerOutput.innerHTML = sanitizeHtml(answerHtml);
        return;
    }
    aiAnswerOutput.innerHTML = sanitizeHtml(renderMarkdown(answerText || ''));
}

function askViaWebSocket(payload, aiAnswerOutput) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(protocol + '//' + window.location.host + '/api/ai/documents/ws');
    let buffer = '';
    let receivedAny = false;
    let sources = [];
    let model = null;
    return new Promise(function (resolve, reject) {
        let settled = false;
        const timeoutId = setTimeout(function () {
            if (settled) return;
            settled = true;
            try { ws.close(); } catch (e) { /* ignore */ }
            reject(new AnswerRequestError('WebSocket timeout'));
        }, 120000);
        const cleanup = function () {
            clearTimeout(timeoutId);
            ws.onopen = null;
            ws.onmessage = null;
            ws.onerror = null;
            ws.onclose = null;
        };
        const safeResolve = function (result) {
            if (settled) return;
            settled = true;
            cleanup();
            try { ws.close(); } catch (e) { /* ignore */ }
            resolve(result);
        };
        const safeReject = function (err) {
            if (settled) return;
            settled = true;
            cleanup();
            try { ws.close(); } catch (e) { /* ignore */ }
            reject(err instanceof Error ? err : new AnswerRequestError(String(err || 'WebSocket failed')));
        };
        ws.onopen = function () {
            try { ws.send(JSON.stringify(payload)); } catch (e) { safeReject(e); }
        };
        ws.onmessage = function (ev) {
            let msg;
            try { msg = JSON.parse(ev.data); } catch (e) { return; }
            if (!msg || !msg.type) return;
            if (msg.type === 'sources') {
                sources = Array.isArray(msg.sources) ? msg.sources : [];
                receivedAny = true;
                return;
            }
            if (msg.type === 'delta') {
                buffer += (msg.text || '');
                receivedAny = true;
                const answerSection = document.getElementById('aiAnswerSection');
                if (answerSection && buffer) {
                    answerSection.classList.remove('hidden');
                    const toggleSourcesBtn = document.getElementById('toggleSources');
                    if (toggleSourcesBtn) toggleSourcesBtn.classList.remove('hidden');
                }
                if (aiAnswerOutput) aiAnswerOutput.textContent = buffer;
                return;
            }
            if (msg.type === 'done') {
                safeResolve({
                    answer: msg.answer || buffer || '',
                    sources: Array.isArray(msg.sources) ? msg.sources : sources,
                    model: msg.model || null,
                });
                return;
            }
            if (msg.type === 'error') {
                safeReject(new AnswerRequestError(msg.message || 'Failed to generate answer.', { application: true }));
            }
        };
        ws.onerror = function () { safeReject(new AnswerRequestError('WebSocket connection error')); };
        ws.onclose = function () {
            if (!receivedAny) safeReject(new AnswerRequestError('WebSocket closed before response'));
            else safeResolve({ answer: buffer || '', sources: sources, model: model });
        };
    });
}

function renderAnswerSources(sources) {
    const sourcesContentEl = document.getElementById('sourcesContent');
    if (!sourcesContentEl) return;
    const sourcesContainer = sourcesContentEl.querySelector('.space-y-2');
    if (!sourcesContainer) return;
    if (sources && sources.length > 0) {
        const shared = document.getElementById('sharedContentArea');
        const advanced = document.getElementById('advancedOptionsContent');
        if (shared) shared.classList.remove('hidden');
        if (advanced) advanced.classList.add('hidden');
        sourcesContentEl.classList.remove('hidden');
        const chevron = document.getElementById('sourcesChevron');
        const advancedChevron = document.getElementById('advancedChevron');
        if (chevron) chevron.style.transform = 'rotate(180deg)';
        if (advancedChevron) advancedChevron.style.transform = 'rotate(0deg)';
    }
    if (!sources || sources.length === 0) {
        sourcesContainer.innerHTML = '<div class="text-sm text-gray-500 italic flex items-center gap-2"><i class="fas fa-info-circle"></i>' +
            escapeHtml(cfg.t.no_sources_found_1203fa96 || '') + '</div>';
        return;
    }
    sourcesContainer.innerHTML = sources.map(function (s, index) {
        const filename = escapeHtml(s.filename || s.title || cfg.t.document_09453598 || '');
        const pageInfo = s.page_label
            ? escapeHtml(s.page_label)
            : (s.page_number != null && s.page_number !== ''
                ? escapeHtml((cfg.t.page_193cfc9b || 'Page') + ' ' + s.page_number)
                : escapeHtml((cfg.t.page_193cfc9b || 'Page') + ' ' + (cfg.t.n_a_382b0f51 || 'N/A')));
        const score = typeof s.score === 'number' ? s.score.toFixed(3) : '';
        const fileIcon = getFileTypeIcon(s.filename || s.title || '');
        return '<div class="flex items-center gap-2 p-2 bg-white rounded border border-gray-200 hover:border-blue-300 hover:shadow-sm transition-all">' +
            '<span class="flex-shrink-0 w-6 h-6 bg-blue-100 text-blue-700 rounded-full flex items-center justify-center text-xs font-semibold">' + (index + 1) + '</span>' +
            '<div class="flex-shrink-0">' + fileIcon + '</div>' +
            '<div class="flex-1 min-w-0 flex items-center gap-2 text-sm text-gray-800">' +
            '<span class="font-medium truncate">' + filename + '</span>' +
            '<span class="text-gray-500">•</span>' +
            '<span class="text-xs text-gray-600 whitespace-nowrap">' + pageInfo + '</span>' +
            (score ? '<span class="text-gray-500">•</span><span class="text-xs text-gray-600 whitespace-nowrap"><i class="fas fa-star text-yellow-500 mr-1"></i>' + escapeHtml(score) + '</span>' : '') +
            '</div></div>';
    }).join('');
}

function showSearchError(aiSearchStatus, errorMsg) {
    if (!aiSearchStatus) return;
    const safeErrorMsg = escapeHtml(errorMsg);
    const statusSpan = aiSearchStatus.querySelector('span');
    if (statusSpan) statusSpan.textContent = (cfg.t.error_3d9f514d || 'Error') + ' ' + errorMsg;
    else {
        aiSearchStatus.innerHTML = '<i class="fas fa-exclamation-triangle text-red-600"></i><span>' +
            escapeHtml(cfg.t.error_3d9f514d || 'Error') + ' ' + safeErrorMsg + '</span>';
    }
    aiSearchStatus.classList.remove('hidden', 'bg-blue-50', 'border-blue-200', 'text-blue-700');
    aiSearchStatus.classList.add('bg-red-50', 'border-red-200', 'text-red-700');
}

function updateSourceCount(count) {
    const sourcesCountEl = document.getElementById('sourcesCount');
    if (!sourcesCountEl) return;
    if (count > 0) {
        sourcesCountEl.textContent = (cfg.t.found_5d695cc2 || '') + ' ' + count + ' ' + (cfg.t.source_s_b7dcde0d || '');
        sourcesCountEl.classList.remove('hidden');
    } else {
        sourcesCountEl.textContent = '';
        sourcesCountEl.classList.add('hidden');
    }
}

export function initAskAi() {
    const toggleAdvancedBtn = document.getElementById('toggleAdvancedOptions');
    const toggleSourcesBtn = document.getElementById('toggleSources');
    const sharedContentArea = document.getElementById('sharedContentArea');
    const advancedOptionsContent = document.getElementById('advancedOptionsContent');
    const sourcesContent = document.getElementById('sourcesContent');
    const advancedChevron = document.getElementById('advancedChevron');
    const sourcesChevron = document.getElementById('sourcesChevron');

    function closeAllSections() {
        if (sharedContentArea) sharedContentArea.classList.add('hidden');
        if (advancedOptionsContent) advancedOptionsContent.classList.add('hidden');
        if (sourcesContent) sourcesContent.classList.add('hidden');
        if (advancedChevron) advancedChevron.style.transform = 'rotate(0deg)';
        if (sourcesChevron) sourcesChevron.style.transform = 'rotate(0deg)';
    }
    function openAdvancedOptions() {
        closeAllSections();
        if (sharedContentArea) sharedContentArea.classList.remove('hidden');
        if (advancedOptionsContent) advancedOptionsContent.classList.remove('hidden');
        if (advancedChevron) advancedChevron.style.transform = 'rotate(180deg)';
    }
    function openSources() {
        closeAllSections();
        if (sharedContentArea) sharedContentArea.classList.remove('hidden');
        if (sourcesContent) sourcesContent.classList.remove('hidden');
        if (sourcesChevron) sourcesChevron.style.transform = 'rotate(180deg)';
    }
    if (toggleAdvancedBtn) {
        toggleAdvancedBtn.addEventListener('click', function () {
            const isOpen = advancedOptionsContent && !advancedOptionsContent.classList.contains('hidden');
            if (isOpen) closeAllSections();
            else openAdvancedOptions();
        });
    }
    if (toggleSourcesBtn) {
        toggleSourcesBtn.addEventListener('click', function () {
            const isOpen = sourcesContent && !sourcesContent.classList.contains('hidden');
            if (isOpen) closeAllSections();
            else openSources();
        });
    }

    const aiSearchForm = document.getElementById('aiSearchForm');
    const aiSearchQuery = document.getElementById('aiSearchQuery');
    const aiSearchMode = document.getElementById('aiSearchMode');
    const aiSearchTopK = document.getElementById('aiSearchTopK');
    const aiSearchMinScore = document.getElementById('aiSearchMinScore');
    const aiSearchFileType = document.getElementById('aiSearchFileType');
    const aiSearchStatus = document.getElementById('aiSearchStatus');
    const aiSearchBtn = document.getElementById('aiSearchBtn');
    const aiAnswerStatus = document.getElementById('aiAnswerStatus');
    const aiAnswerOutput = document.getElementById('aiAnswerOutput');
    const aiSearchBtnInitialHtml = aiSearchBtn ? aiSearchBtn.innerHTML : '';
    if (!aiSearchForm) return;

    aiSearchForm.addEventListener('submit', async function (e) {
        e.preventDefault();
        const query = (aiSearchQuery && aiSearchQuery.value || '').trim();
        if (!query) {
            if (aiSearchStatus) {
                const statusSpan = aiSearchStatus.querySelector('span');
                if (statusSpan) statusSpan.textContent = cfg.t.please_enter_a_query_4ad9a6c1 || '';
                else {
                    aiSearchStatus.innerHTML = '<i class="fas fa-exclamation-circle text-yellow-600"></i><span>' +
                        escapeHtml(cfg.t.please_enter_a_query_4ad9a6c1 || '') + '</span>';
                }
                aiSearchStatus.classList.remove('hidden', 'bg-blue-50', 'border-blue-200', 'text-blue-700');
                aiSearchStatus.classList.add('bg-yellow-50', 'border-yellow-200', 'text-yellow-700');
            }
            return;
        }
        if (aiSearchStatus) {
            aiSearchStatus.classList.remove('bg-yellow-50', 'border-yellow-200', 'text-yellow-700', 'bg-red-50', 'border-red-200', 'text-red-700');
            aiSearchStatus.classList.add('bg-blue-50', 'border-blue-200', 'text-blue-700');
        }
        const submitBtn = aiSearchBtn;
        if (!submitBtn) return;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin text-lg" style="color: #2563eb !important;"></i>';
        const sourcesContentEl = document.getElementById('sourcesContent');
        const sourcesContainer = sourcesContentEl ? sourcesContentEl.querySelector('.space-y-2') : null;
        if (sourcesContainer) sourcesContainer.innerHTML = '';
        updateSourceCount(0);
        if (toggleSourcesBtn) toggleSourcesBtn.classList.add('hidden');
        if (sourcesContentEl && !sourcesContentEl.classList.contains('hidden')) closeAllSections();
        const answerSection = document.getElementById('aiAnswerSection');
        if (answerSection) answerSection.classList.remove('hidden');
        if (aiAnswerOutput) {
            aiAnswerOutput.innerHTML = '<div class="flex items-center gap-2 text-gray-500"><span>' +
                escapeHtml(cfg.t.typing_066182d6 || '') +
                '</span><span class="ai-typing-indicator" aria-hidden="true"><span></span><span></span><span></span></span></div>';
        }
        setAnswerStatus(aiAnswerStatus, {});
        const issues = [];
        const requestPayload = {
            type: 'answer',
            query: query,
            top_k: parseInt((aiSearchTopK && aiSearchTopK.value) || '5', 10),
            min_score: parseFloat((aiSearchMinScore && aiSearchMinScore.value) || '0.35'),
            file_type: (aiSearchFileType && aiSearchFileType.value) || '',
            search_mode: (aiSearchMode && aiSearchMode.value) || 'hybrid',
        };
        try {
            const wsFromPage = document.body && document.body.getAttribute('data-chat-websocket-enabled');
            const wsEnabled = wsFromPage !== null ? (wsFromPage === 'true') : (window.CHAT_WEBSOCKET_ENABLED === true);
            if (!wsEnabled || typeof WebSocket === 'undefined') {
                throw new AnswerRequestError(wsEnabled ? 'WebSocket not supported' : 'WebSocket disabled');
            }
            let wsResult;
            try {
                wsResult = await askViaWebSocket(requestPayload, aiAnswerOutput);
            } catch (error) {
                if (error && error.application) throw error;
                issues.push('Using standard connection');
                throw error;
            }
            const wsModelInfo = classifyModel(wsResult.model);
            if (wsModelInfo.kind === 'error') issues.push('Backend reported an error model');
            else if (wsModelInfo.kind === 'unknown') issues.push('Model not reported');
            ensureAnswerShown(aiAnswerOutput, wsResult.answer, null);
            renderAnswerSources(wsResult.sources);
            updateSourceCount((wsResult.sources && wsResult.sources.length) || 0);
            if (toggleSourcesBtn && wsResult.sources && wsResult.sources.length) toggleSourcesBtn.classList.remove('hidden');
            setAnswerStatus(aiAnswerStatus, { transport: 'WebSocket', model: wsModelInfo.label, issues: issues });
        } catch (error) {
            if (error && error.application) {
                showSearchError(aiSearchStatus, error.message);
                setAnswerStatus(aiAnswerStatus, { transport: 'WebSocket', model: null, issues: [error.message] });
            } else {
                try {
                    if (!issues.includes('Using standard connection')) issues.push('Using standard connection');
                    const response = await csrfFetch('/api/ai/documents/answer', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
                        body: JSON.stringify({
                            query: requestPayload.query,
                            top_k: requestPayload.top_k,
                            min_score: requestPayload.min_score,
                            file_type: requestPayload.file_type,
                            search_mode: requestPayload.search_mode,
                        }),
                    });
                    const result = await response.json();
                    if (result.success) {
                        const httpModelInfo = classifyModel(result.model);
                        if (httpModelInfo.kind === 'error') issues.push('Backend reported an error model');
                        else if (httpModelInfo.kind === 'unknown') issues.push('Model not reported');
                        ensureAnswerShown(aiAnswerOutput, result.answer || '', result.answer_html);
                        const sources = Array.isArray(result.sources) ? result.sources : [];
                        renderAnswerSources(sources);
                        updateSourceCount(sources.length);
                        if (toggleSourcesBtn && sources.length) toggleSourcesBtn.classList.remove('hidden');
                        setAnswerStatus(aiAnswerStatus, { transport: 'HTTP', model: httpModelInfo.label, issues: issues });
                    } else {
                        const errorMsg = result.error || cfg.t.failed_to_generate_answer_9c78619e || '';
                        showSearchError(aiSearchStatus, errorMsg);
                        issues.push(result.error || 'Request failed');
                        setAnswerStatus(aiAnswerStatus, { transport: 'HTTP', model: null, issues: issues });
                    }
                } catch (e2) {
                    console.error('AI query error:', e2);
                    const errorMsg = e2.message || cfg.t.failed_to_process_request_df530c1a || '';
                    showSearchError(aiSearchStatus, errorMsg);
                    issues.push(e2.message || 'HTTP request failed');
                    setAnswerStatus(aiAnswerStatus, { transport: 'HTTP', model: null, issues: issues });
                }
            }
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = aiSearchBtnInitialHtml || '<i class="fas fa-paper-plane text-lg" style="color: #2563eb !important;"></i>';
        }
    });
}
