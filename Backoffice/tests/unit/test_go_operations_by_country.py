"""Per-country split of a worldwide GO appeal list."""

from plugins.fdrs.services.go_operations import operations_payloads_from_appeals


def test_splits_active_appeals_by_country():
    payloads = operations_payloads_from_appeals([
        {
            'status': 0,
            'name': 'Floods',
            'code': 'MDRXX001',
            'atype_display': 'DREF',
            'dtype': {'name': 'Flood'},
            'country': {'iso3': 'bgd', 'name': 'Bangladesh'},
            'num_beneficiaries': 10,
            'amount_requested': 5,
            'amount_funded': 2,
            'start_date': '2024-01-02',
        },
        {
            'status': 1,
            'name': 'Closed',
            'country': {'iso3': 'BGD', 'name': 'Bangladesh'},
        },
        {
            'status': 0,
            'name': 'Earthquake',
            'atype_display': 'Emergency Appeal',
            'country': {'iso3': 'TUR', 'name': 'Türkiye'},
            'num_beneficiaries': 3,
            'amount_requested': 8,
            'amount_funded': 1,
            'start_date': '2024-02-01',
        },
    ])

    assert set(payloads) == {'BGD', 'TUR'}
    bangladesh = payloads['BGD']
    assert bangladesh['summary']['active_drefs'] == 1
    assert bangladesh['summary']['active_appeals'] == 0
    assert bangladesh['summary']['people_targeted'] == 10
    assert bangladesh['operations'][0]['name'] == 'Floods'
    assert bangladesh['available'] is True
    assert payloads['TUR']['summary']['active_appeals'] == 1
