// Infinite scroll for per-field change-history tooltips on the entry form.

const LOAD_THRESHOLD_PX = 48;
const PAGE_LIMIT = 8;

function historyUrl(aesId, fieldId, fieldKind, offset) {
  const params = new URLSearchParams({
    field_id: String(fieldId),
    field_kind: String(fieldKind || 'form_item'),
    offset: String(offset || 0),
    limit: String(PAGE_LIMIT),
  });
  return `/api/forms/assignment/${encodeURIComponent(aesId)}/field-history?${params}`;
}

async function fetchHistoryPage(panel) {
  if (!panel || panel.dataset.historyLoading === '1') return;
  if (panel.dataset.historyHasMore !== '1') return;

  const aesId = panel.dataset.historyAesId;
  const fieldId = panel.dataset.historyFieldId;
  const fieldKind = panel.dataset.historyFieldKind || 'form_item';
  const offset = Number(panel.dataset.historyOffset || 0);
  if (!aesId || !fieldId) return;

  panel.dataset.historyLoading = '1';
  const sentinel = panel.querySelector('.history-load-more');
  const spinner = sentinel && sentinel.querySelector('.history-load-more-spinner');
  if (spinner) spinner.hidden = false;

  try {
    const response = await fetch(historyUrl(aesId, fieldId, fieldKind, offset), {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const html = (data && data.html) || '';
    const hasMore = !!(data && data.has_more);
    const nextOffset = data && data.next_offset != null ? Number(data.next_offset) : offset;

    if (html) {
      const wrap = document.createElement('div');
      wrap.innerHTML = html;
      const fragment = document.createDocumentFragment();
      while (wrap.firstChild) fragment.appendChild(wrap.firstChild);
      if (sentinel) {
        panel.insertBefore(fragment, sentinel);
      } else {
        panel.appendChild(fragment);
      }
    }

    panel.dataset.historyOffset = String(nextOffset);
    panel.dataset.historyHasMore = hasMore ? '1' : '0';
    if (!hasMore && sentinel) sentinel.remove();
    // Keep filling until the panel can scroll (or history is exhausted).
    if (hasMore) {
      requestAnimationFrame(() => maybeLoadMore(panel));
    }
  } catch (err) {
    // Keep the sentinel so the user can scroll again to retry.
    // eslint-disable-next-line no-console
    console.warn('[field-history] failed to load more changes', err);
  } finally {
    panel.dataset.historyLoading = '0';
    if (spinner) spinner.hidden = true;
  }
}

function maybeLoadMore(panel) {
  if (!panel || panel.dataset.historyHasMore !== '1') return;
  if (panel.scrollHeight <= panel.clientHeight) {
    // Content does not overflow yet but more pages exist — fetch until it scrolls
    // or history is exhausted.
    fetchHistoryPage(panel);
    return;
  }
  if (panel.scrollTop + panel.clientHeight >= panel.scrollHeight - LOAD_THRESHOLD_PX) {
    fetchHistoryPage(panel);
  }
}

function bindHistoryPanel(panel) {
  if (!panel || panel.dataset.historyScrollBound === '1') return;
  panel.dataset.historyScrollBound = '1';
  panel.addEventListener('scroll', () => maybeLoadMore(panel), { passive: true });
}

export function bindFieldHistoryScroll(container) {
  const panel = container && container.querySelector
    ? container.querySelector('.tooltip-text')
    : null;
  if (!panel || !panel.dataset.historyAesId) return;
  bindHistoryPanel(panel);
  // When the tooltip first opens with more pages than fit, preload until scrollable.
  maybeLoadMore(panel);
}

export function initFieldHistory() {
  document.querySelectorAll('.entry-item-history .tooltip-text[data-history-aes-id]').forEach(bindHistoryPanel);
}
