const assert = require('node:assert/strict');
const test = require('node:test');

const core = require('../../app/static/js/data-exploration/data-exploration-analysis-core.js');

const countries = [
    { id: 1, name: 'Freedonia', region: 'Europe' },
    { id: 2, name: 'Sylvania', region: 'Africa' }
];

function indicator(id, bankId, label, unit = 'people', options = ['sex'], allowDisabilityQuestions = false) {
    return {
        id,
        label,
        unit,
        allowed_disaggregation_options: options,
        allow_disability_questions: allowDisabilityQuestions,
        bank_details: { id: bankId, name: label, unit }
    };
}

test('processDisaggregationData separates eligible missing, total-only, and disaggregated rows', () => {
    const formItems = [
        indicator(1, 1001, 'People reached'),
        indicator(2, 1002, 'People trained'),
        { id: 99, label: 'Narrative question', type: 'text' }
    ];
    const rows = [
        {
            form_item_id: 1,
            country_id: 1,
            period_name: 'FDRS 2023',
            disaggregation_data: { mode: 'sex', values: { female: 6, male: 4 } }
        },
        {
            form_item_id: 2,
            country_id: 1,
            period_name: 'FDRS 2023',
            value: '999',
            num_value: 42
        },
        {
            form_item_id: 1,
            country_id: 1,
            period_name: 'FDRS 2023',
            is_missing: true,
            data_status: 'missing'
        },
        {
            form_item_id: 99,
            country_id: 1,
            period_name: 'FDRS 2023',
            value: 'This scalar question must not be counted'
        }
    ];

    const processed = core.processDisaggregationData(rows, formItems, countries);

    assert.equal(processed.coverageSummary.eligibleRows, 3);
    assert.equal(processed.coverageSummary.disaggregatedRows, 1);
    assert.equal(processed.coverageSummary.totalOnlyRows, 1);
    assert.equal(processed.coverageSummary.missingRows, 1);
    assert.equal(processed.coverageSummary.overallDisaggregationPercentage, 33);

    const freedonia = processed.countryDisaggregation.find(item => item.label === 'Freedonia');
    assert.equal(freedonia.totalItems, 3);
    assert.equal(freedonia.disaggregatedItems, 1);
    assert.equal(freedonia.totalOnly, 1);
    assert.equal(freedonia.missingItems, 1);
    assert.equal(freedonia.totalValue, 52);
});

test('sex_age rows count toward sex, age, and sex-age coverage', () => {
    const formItems = [indicator(1, 1001, 'People reached')];
    const rows = [{
        form_item_id: 1,
        country_id: 1,
        period_name: '2024 Annual',
        disaggregation_data: {
            mode: 'sex_age',
            values: {
                female_18_59: 7,
                male_18_59: 3
            }
        }
    }];

    const processed = core.processDisaggregationData(rows, formItems, countries);

    assert.equal(processed.coverageSummary.sexCoveragePercentage, 100);
    assert.equal(processed.coverageSummary.ageCoveragePercentage, 100);
    assert.equal(processed.coverageSummary.sexAgeCoveragePercentage, 100);
    assert.deepEqual(processed.bySex, [
        { label: 'Female', value: 7 },
        { label: 'Male', value: 3 }
    ]);
    assert.deepEqual(processed.byAge, [{ label: '18-59 years', value: 10 }]);
});

test('women participation uses FDRS indicator ids and numeric years for trends', () => {
    const formItems = [indicator(10, 722, 'Female members of governing board')];
    const rows = [
        {
            form_item_id: 10,
            country_id: 1,
            period_name: 'FDRS 2023',
            disaggregation_data: { mode: 'sex', values: { female: 4, male: 6 } }
        },
        {
            form_item_id: 10,
            country_id: 1,
            period_name: 'FDRS 2016',
            disaggregation_data: { mode: 'sex', values: { female: 1, male: 1 } }
        }
    ];

    const processed = core.processDisaggregationData(rows, formItems, countries);
    const leadership = processed.womenInLeadership.comparison.find(item => item.label === 'Leadership Roles');

    assert.equal(leadership.percentage, 42);
    assert.deepEqual(processed.womenInLeadership.trends, [{
        label: 'FDRS 2023',
        leadershipPercentage: 40,
        volunteeringPercentage: 0,
        staffPercentage: 0
    }]);
});

test('processDisaggregationData includes loaded countries even when they have no eligible data', () => {
    const formItems = [indicator(1, 1001, 'People reached')];
    const rows = [{
        form_item_id: 1,
        country_id: 1,
        period_name: 'FDRS 2024',
        disaggregation_data: { mode: 'sex', values: { female: 2, male: 3 } }
    }];

    const processed = core.processDisaggregationData(rows, formItems, countries);

    assert.deepEqual(processed.countryUniverse, [
        { label: 'Sylvania', region: 'Africa' },
        { label: 'Freedonia', region: 'Europe' }
    ]);
    assert.equal(processed.countryDisaggregationByYear[2024].Freedonia.totalItems, 1);
});

test('disability-only rows count toward overall disaggregation coverage', () => {
    const formItems = [indicator(1, 1001, 'Volunteers', 'volunteers', ['total'], true)];
    const rows = [
        {
            form_item_id: 1,
            country_id: 1,
            period_name: 'FDRS 2024',
            disaggregation_data: {
                mode: 'total',
                values: {
                    disability: {
                        disaggregated_by_disability: true,
                        washington_group_compliant: true
                    }
                }
            }
        },
        {
            form_item_id: 1,
            country_id: 1,
            period_name: 'FDRS 2024',
            disaggregation_data: {
                mode: 'total',
                values: {
                    disability: {
                        disaggregated_by_disability: false
                    }
                }
            }
        }
    ];

    const processed = core.processDisaggregationData(rows, formItems, countries);
    const freedonia = processed.countryDisaggregation.find(item => item.label === 'Freedonia');

    assert.equal(processed.coverageSummary.eligibleRows, 2);
    assert.equal(processed.coverageSummary.totalOnlyRows, 0);
    assert.equal(processed.coverageSummary.disaggregatedRows, 2);
    assert.equal(processed.coverageSummary.overallDisaggregationPercentage, 100);
    assert.equal(freedonia.disaggregatedItems, 2);
    assert.equal(freedonia.overallDisaggregation, 100);
});
