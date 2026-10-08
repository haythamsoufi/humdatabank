"""Matrix row headers: periods stay in calendar order."""

from app.utils.matrix_row_order import sort_matrix_display_rows


def test_period_row_headers_sort_chronologically():
    rows = [
        {"row_display": "Jan-Jun 2026"},
        {"row_display": "2025"},
        {"row_display": "Jul-Dec 2025"},
        {"row_display": "Q1 2026"},
        {"row_display": "2026"},
    ]
    ordered = [row["row_display"] for row in sort_matrix_display_rows(rows)]
    assert ordered == ["2025", "Jul-Dec 2025", "2026", "Jan-Jun 2026", "Q1 2026"]


def test_period_rows_stay_ahead_of_names():
    rows = [
        {"row_display": "Zambia"},
        {"row_display": "2026"},
        {"row_display": "Botswana"},
        {"row_display": "2025"},
    ]
    ordered = [row["row_display"] for row in sort_matrix_display_rows(rows)]
    assert ordered == ["2025", "2026", "Botswana", "Zambia"]


def test_name_rows_stay_alphabetical_with_numeric_runs():
    rows = [
        {"row_display": "Zambia"},
        {"row_display": "Botswana"},
        {"row_display": "Row 10"},
        {"row_display": "Row 2"},
    ]
    ordered = [row["row_display"] for row in sort_matrix_display_rows(rows)]
    assert ordered == ["Botswana", "Row 2", "Row 10", "Zambia"]
