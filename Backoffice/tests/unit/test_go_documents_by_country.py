"""Grouping one GO document feed into per-country lists."""

from plugins.fdrs.services.go_operation_documents import group_go_documents


def test_groups_appeal_documents_and_situation_reports_by_country():
    grouped = group_go_documents(
        appeal_items=[
            {
                'iso': 'BD',
                'document_url': 'https://goadmin.ifrc.org/floods.pdf',
                'type': 'Appeal',
                'name': 'Floods appeal',
                'created_at': '2024-03-01',
                'appeal': {'code': 'MDRBD001'},
            },
        ],
        event_items=[
            {'id': 9, 'name': 'Floods', 'countries': [{'iso3': 'BGD'}]},
        ],
        report_items=[
            {
                'visibility': 3,
                'event': 9,
                'document_url': 'https://go.ifrc.org/sitrep.pdf',
                'name': 'Sitrep 1',
                'created_at': '2024-04-01',
                'type': {'type': 'Situation Report'},
            },
        ],
        appeal_name_items=[
            {
                'code': 'MDRBD001',
                'name': 'Bangladesh Floods',
                'country': {'iso3': 'BGD'},
            },
        ],
        iso2_to_iso3={'BD': 'BGD'},
    )

    documents = grouped['BGD']
    assert [row['title'] for row in documents] == ['Floods appeal', 'Sitrep 1']
    appeal = next(row for row in documents if row['title'] == 'Floods appeal')
    assert appeal['emergency'] == 'Bangladesh Floods'
    assert 'TUR' not in grouped
