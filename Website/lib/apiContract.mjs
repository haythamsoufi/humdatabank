/**
 * Adapt Backoffice API payloads to the shapes the public website already renders.
 *
 * /api/v1/data returns percentage facts on a 0–1 scale. Form entry and the FDRS
 * published feed keep 0–100. Dashboards display the stored 0–100 scale.
 *
 * GET /api/v1/fdrs/published-data is the public FDRS feed (published snapshot
 * only). Rows are normalized so country, template, and disaggregation consumers
 * can keep using the same fields as /api/v1/data.
 */

const PERCENTAGE_TYPES = new Set(['percentage', 'percent', 'pct']);

export const FDRS_TEMPLATE_ID = 21;

const SCALAR_FIELDS = ['value', 'num_value', 'answer_value', 'prefilled_value', 'imputed_value'];
const DISAGG_FIELDS = [
  'disaggregation_data',
  'prefilled_disaggregation_data',
  'imputed_disaggregation_data',
  'prefilled_disagg_data',
  'imputed_disagg_data',
];

export function isPercentageType(value) {
  if (value == null) return false;
  return PERCENTAGE_TYPES.has(String(value).trim().toLowerCase());
}

export function isPercentageFormItem(item) {
  if (!item || typeof item !== 'object') return false;
  const bank = item.bank_details;
  return (
    isPercentageType(item.question_type)
    || isPercentageType(bank && bank.type)
    || isPercentageType(item.type)
  );
}

export function stampFormItemTemplateId(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => {
    if (!item || typeof item !== 'object') return item;
    if (item.template_id != null && item.template_id !== '') return item;
    const nestedId = item.template && item.template.id;
    if (nestedId == null) return item;
    return { ...item, template_id: nestedId };
  });
}

function scaleNumeric(value) {
  if (typeof value === 'number' && Number.isFinite(value)) return value * 100;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed * 100;
  }
  return value;
}

function scaleTree(value) {
  if (Array.isArray(value)) return value.map(scaleTree);
  if (value && typeof value === 'object') {
    const out = {};
    for (const [key, child] of Object.entries(value)) {
      out[key] = key === 'mode' ? child : scaleTree(child);
    }
    return out;
  }
  return scaleNumeric(value);
}

export function restoreStoredPercentageScale(rows, formItems) {
  const percentageIds = new Set();
  for (const item of formItems || []) {
    if (item && item.id != null && isPercentageFormItem(item)) {
      percentageIds.add(Number(item.id));
    }
  }
  if (!percentageIds.size || !Array.isArray(rows)) return rows || [];
  return rows.map((row) => {
    if (!row || typeof row !== 'object') return row;
    if (!percentageIds.has(Number(row.form_item_id))) return row;
    const next = { ...row };
    for (const key of SCALAR_FIELDS) {
      if (next[key] != null) next[key] = scaleTree(next[key]);
    }
    for (const key of DISAGG_FIELDS) {
      if (next[key] != null) next[key] = scaleTree(next[key]);
    }
    return next;
  });
}

/** In-place-safe copy of a flat /api/v1/data JSON body. */
export function adaptFlatDataPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload;
  const formItems = stampFormItemTemplateId(payload.form_items);
  return {
    ...payload,
    form_items: formItems,
    data: restoreStoredPercentageScale(payload.data, formItems),
  };
}

export function normalizePublishedFdrsRow(row, templateId = FDRS_TEMPLATE_ID) {
  if (!row || typeof row !== 'object') return null;
  const id = row.id != null
    ? row.id
    : `published:${row.submission_id}:${row.form_item_id}`;
  return {
    id,
    field_type: 'static',
    submission_type: 'assigned',
    submission_id: row.submission_id,
    assigned_form_id: row.assignment_id,
    assignment_id: row.assignment_id,
    template_id: templateId,
    form_item_id: row.form_item_id,
    stable_key: row.stable_key ?? null,
    period_name: row.period_name ?? null,
    country_id: row.country_id ?? null,
    iso2: row.iso2 ?? null,
    iso3: row.iso3 ?? null,
    indicator_bank_id: row.indicator_bank_id ?? null,
    item_label: row.item_label ?? null,
    value: row.value ?? null,
    num_value: row.num_value ?? null,
    answer_value: row.value ?? null,
    disaggregation_data: row.disaggregation_data ?? null,
    data_status: row.data_status ?? null,
    value_source: row.value_source ?? null,
    published_at: row.published_at ?? null,
    country_info: {
      id: row.country_id ?? null,
      name: row.country_name ?? null,
      iso2: row.iso2 ?? null,
      iso3: row.iso3 ?? null,
    },
  };
}

export function publishedFdrsSearchParams(filters = {}, page = 1, perPage = 10000) {
  const params = { page: String(page), per_page: String(perPage) };
  const names = [
    'period_name',
    'indicator_bank_id',
    'country_id',
    'country_iso2',
    'country_iso3',
    'form_item_id',
    'assignment_id',
  ];
  for (const name of names) {
    const value = filters[name];
    if (value != null && value !== '') params[name] = String(value);
  }
  return params;
}

/**
 * Page through the published feed. `fetchPage(page, perPage)` resolves to the
 * JSON body, or null when the feed cannot be used (caller should keep live rows).
 */
export async function collectPublishedFdrsRows(fetchPage, templateId = FDRS_TEMPLATE_ID) {
  const rows = [];
  let page = 1;
  let totalPages = 1;
  const perPage = 10000;
  while (page <= totalPages && page <= 50) {
    const json = await fetchPage(page, perPage);
    if (!json || typeof json !== 'object') return null;
    const batch = Array.isArray(json.data) ? json.data : [];
    for (const row of batch) {
      const normalized = normalizePublishedFdrsRow(row, templateId);
      if (normalized) rows.push(normalized);
    }
    const meta = json.meta || {};
    totalPages = Number(meta.total_pages || 1);
    if (!batch.length) break;
    page += 1;
  }
  return rows;
}

export function replaceFdrsRowsWithPublished(dataRows, publishedRows, templateId = FDRS_TEMPLATE_ID) {
  const kept = (Array.isArray(dataRows) ? dataRows : []).filter(
    (row) => Number(row && row.template_id) !== Number(templateId),
  );
  return kept.concat(publishedRows || []);
}

export function shouldUsePublishedFdrsFeed(templateId, filters = {}) {
  if (Number(templateId) !== FDRS_TEMPLATE_ID) return false;
  if (filters.published === false || filters.published === 'false') return false;
  if (filters.submission_type && filters.submission_type !== 'assigned') return false;
  return true;
}

/**
 * Page form items for a template. `fetchPage(page)` resolves to the JSON body,
 * or null when that page cannot be used.
 */
export async function collectFormItems(fetchPage) {
  const items = [];
  let page = 1;
  let totalPages = 1;
  while (page <= totalPages && page <= 20) {
    const json = await fetchPage(page);
    if (!json || typeof json !== 'object') break;
    const batch = Array.isArray(json.form_items) ? json.form_items : [];
    items.push(...batch);
    totalPages = Number(json.total_pages || 1);
    if (!batch.length) break;
    page += 1;
  }
  return stampFormItemTemplateId(items);
}
