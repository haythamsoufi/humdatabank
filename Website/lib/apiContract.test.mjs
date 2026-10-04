import test from 'node:test';
import assert from 'node:assert/strict';

import {
  adaptFlatDataPayload,
  collectPublishedFdrsRows,
  isPercentageFormItem,
  normalizePublishedFdrsRow,
  replaceFdrsRowsWithPublished,
  restoreStoredPercentageScale,
  collectFormItems,
  shouldUsePublishedFdrsFeed,
} from './apiContract.mjs';

test('percentage form items are detected from question type or indicator bank type', () => {
  assert.equal(isPercentageFormItem({ question_type: 'percentage' }), true);
  assert.equal(isPercentageFormItem({ bank_details: { type: 'Percent' } }), true);
  assert.equal(isPercentageFormItem({ type: 'indicator', bank_details: { type: 'number' } }), false);
});

test('stored percentage scale is restored only for percentage rows', () => {
  const formItems = [
    { id: 7, question_type: 'percentage' },
    { id: 8, bank_details: { type: 'number' } },
  ];
  const rows = restoreStoredPercentageScale([
    {
      form_item_id: 7,
      value: 0.25,
      num_value: 0.25,
      disaggregation_data: { mode: 'sex', values: { female: 0.1, male: 0.15 } },
    },
    { form_item_id: 8, value: 12, num_value: 12 },
  ], formItems);

  assert.equal(rows[0].value, 25);
  assert.equal(rows[0].num_value, 25);
  assert.equal(rows[0].disaggregation_data.mode, 'sex');
  assert.equal(rows[0].disaggregation_data.values.female, 10);
  assert.equal(rows[1].value, 12);
});

test('flat data payload stamps template id and restores percentages', () => {
  const adapted = adaptFlatDataPayload({
    data: [{ form_item_id: 3, value: 1 }],
    form_items: [{ id: 3, type: 'percentage', template: { id: 21 } }],
    total_items: 1,
  });
  assert.equal(adapted.form_items[0].template_id, 21);
  assert.equal(adapted.data[0].value, 100);
  assert.equal(adapted.total_items, 1);
});

test('published FDRS rows keep the 0-100 scale and gain country_info', () => {
  const row = normalizePublishedFdrsRow({
    id: 55,
    submission_id: 9,
    assignment_id: 4,
    form_item_id: 3,
    period_name: '2024',
    country_id: 2,
    country_name: 'Kenya',
    iso3: 'KEN',
    iso2: 'KE',
    indicator_bank_id: 729,
    value: '25',
    num_value: 25,
    disaggregation_data: { mode: 'total', values: { total: 25 } },
    data_status: 'available',
    value_source: 'reported',
  });
  assert.equal(row.template_id, 21);
  assert.equal(row.value, '25');
  assert.equal(row.answer_value, '25');
  assert.equal(row.country_info.name, 'Kenya');
  assert.equal(row.country_info.iso3, 'KEN');
  assert.equal(row.indicator_bank_id, 729);
  assert.equal(row.submission_type, 'assigned');
});

test('published rows replace only the FDRS template', () => {
  const merged = replaceFdrsRowsWithPublished(
    [
      { template_id: 21, value: '999' },
      { template_id: 33, value: '7' },
    ],
    [{ template_id: 21, value: '40' }],
  );
  assert.deepEqual(merged.map((row) => row.value), ['7', '40']);
});

test('published feed is used for default FDRS assigned reads', () => {
  assert.equal(shouldUsePublishedFdrsFeed(21, {}), true);
  assert.equal(shouldUsePublishedFdrsFeed(33, {}), false);
  assert.equal(shouldUsePublishedFdrsFeed(21, { submission_type: 'public' }), false);
  assert.equal(shouldUsePublishedFdrsFeed(21, { published: false }), false);
  assert.equal(shouldUsePublishedFdrsFeed(21, { published: 'false' }), false);
});

test('collectFormItems pages and stamps template id', async () => {
  const pages = {
    1: {
      form_items: [{ id: 3, template: { id: 21 } }],
      total_pages: 2,
    },
    2: {
      form_items: [{ id: 4, template_id: 21 }],
      total_pages: 2,
    },
  };
  const items = await collectFormItems(async (page) => pages[page]);
  assert.equal(items.length, 2);
  assert.equal(items[0].template_id, 21);
  assert.equal(items[1].id, 4);
});

test('collectPublishedFdrsRows pages until total_pages', async () => {
  const pages = {
    1: { data: [{ id: 1, value: '1', country_name: 'A' }], meta: { total_pages: 2 } },
    2: { data: [{ id: 2, value: '2', country_name: 'B' }], meta: { total_pages: 2 } },
  };
  const rows = await collectPublishedFdrsRows(async (page) => pages[page]);
  assert.equal(rows.length, 2);
  assert.equal(rows[1].country_info.name, 'B');
});
