"""Items-table matrix labels keep column groups and subgroups."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).resolve().parents[3] / "app" / "templates"


def _render(item):
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.from_string(
        "{% from 'components/_builder_items.html' import matrix_column_outline %}"
        "{{ matrix_column_outline(item) }}"
    )
    return template.render(item=item)


def _item(columns, column_groups=None):
    matrix_config = {"columns": columns}
    if column_groups is not None:
        matrix_config["column_groups"] = column_groups
    return {"config": {"matrix_config": matrix_config}}


def test_ungrouped_columns_stay_a_flat_list():
    html = _render(_item([
        {"name": "amount", "name_translations": {"en": "Amount"}},
        {"name": "note"},
        "Legacy",
    ]))
    assert "fb-matrix-col-group" not in html
    assert "Amount, note, Legacy" in html


def test_groups_and_subgroups_outline_column_order():
    html = _render(_item(
        [
            {
                "name": "sp2",
                "name_translations": {"en": "Response - Disasters and Crises"},
                "group": "[assignment_year]",
                "subgroup": "fun_req",
            },
            {
                "name": "sp1",
                "name_translations": {"en": "Resilience - Climate and environment"},
                "group": "[assignment_year]",
                "subgroup": "fun_req",
            },
            {
                "name": "confirmed",
                "name_translations": {"en": "Confirmed Funding"},
                "group": "[assignment_year]",
            },
            {
                "name": "sp2_next",
                "name_translations": {"en": "Response - Disasters and Crises"},
                "group": "year_[[assignment_year]+1]",
                "subgroup": "fun_req",
            },
            {"name": "plain"},
        ],
        {
            "[assignment_year]": {
                "en": "[assignment_year]",
                "header_color": "#5f97c9",
                "apply_color_to_headers": True,
            },
            "[assignment_year]::fun_req": {
                "en": "Funding Requirements",
                "header_color": "#b5d4ef",
            },
            "year_[[assignment_year]+1]": {"en": "[[assignment_year]+1]"},
            "year_[[assignment_year]+1]::fun_req": {"en": "Funding Requirements"},
        },
    ))

    assert html.count('class="fb-matrix-col-group"') == 2
    assert "fun_req" not in html
    assert "[assignment_year]" in html
    assert "[[assignment_year]+1]" in html
    assert "Funding Requirements" in html
    assert "Response - Disasters and Crises, Resilience - Climate and environment" in html
    # Confirmed Funding sits on the group, outside the subgroup block.
    subgroup = html.split('class="fb-matrix-col-group__sub"', 1)[1].split("</span>", 2)
    subgroup_html = "".join(subgroup[:2])
    assert "Funding Requirements" in subgroup_html
    assert "Confirmed Funding" not in subgroup_html
    assert ">plain<" in html
    assert html.index("Confirmed Funding") < html.index("[[assignment_year]+1]")
    assert html.index("[[assignment_year]+1]") < html.index(">plain<")
    assert 'style="background-color: #5f97c9"' in html
    assert 'style="background-color: #b5d4ef"' in html
    # Ungrouped columns stay outside every group.
    assert html.rindex('class="fb-matrix-col-flat"') > html.rindex('class="fb-matrix-col-group"')


def test_group_label_falls_back_to_the_key_and_rejects_bad_colors():
    html = _render(_item(
        [{"name": "amount", "name_translations": {"en": "Amount"}, "group": "2026", "subgroup": "q1"}],
        {
            "2026": {"fr": "Deux mille", "header_color": "red;}"},
            "2026::q1": {"header_color": "#GGGGGG"},
        },
    ))
    assert ">2026<" in html
    assert ">q1<" in html
    assert "Deux mille" not in html
    assert "background-color" not in html
    assert "Amount" in html


def test_column_labels_are_escaped():
    html = _render(_item([
        {"name": "<script>", "group": "A & B", "name_translations": {"en": "A < B"}},
    ], {"A & B": {"en": "A & B"}}))
    assert "<script>" not in html
    assert "A &lt; B" in html
    assert "A &amp; B" in html
