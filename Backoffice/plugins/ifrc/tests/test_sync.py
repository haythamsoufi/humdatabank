"""Compiler and status rules for the PPP Kobo sync."""

from __future__ import annotations

from datetime import datetime

from plugins.ifrc.ppp import sync as ppp


def _row(type_name, name, label=None, list_name=None):
    row = {"type": type_name, "name": name}
    if label is not None:
        row["label"] = [label, "", "", ""]
    if list_name:
        row["select_from_list_name"] = list_name
        row["type"] = type_name.split()[0]
    return row


def test_disagg_names_keep_indicator_suffix_out_of_age_bands():
    assert ppp.parse_disagg_name("male_0-5_1.1") == {"kind": "male", "band": "0-5", "suffix": "1.1"}
    assert ppp.parse_disagg_name("female_80_1.1") == {"kind": "female", "band": "80+", "suffix": "1.1"}
    assert ppp.parse_disagg_name("female_4") == {"kind": "female", "band": None, "suffix": "4"}
    assert ppp.parse_disagg_name("total_1.2") == {"kind": "total", "band": None, "suffix": "1.2"}
    assert ppp.parse_disagg_name("unknown_6-12_1.2")["band"] == "6-12"
    assert ppp.parse_disagg_name("unique_indiv_country_pop") is None


def test_validation_status_maps_only_approved_and_on_hold():
    assert ppp.assignment_status_for_bucket(ppp.kobo_validation_bucket({"uid": "validation_status_approved"})) == "approved"
    assert ppp.assignment_status_for_bucket(ppp.kobo_validation_bucket("On hold")) == "submitted"
    assert ppp.assignment_status_for_bucket(ppp.kobo_validation_bucket("validation_status_not_approved")) is None
    assert ppp.assignment_status_for_bucket(ppp.kobo_validation_bucket("")) is None
    assert ppp.assignment_status_for_bucket(ppp.kobo_validation_bucket(None)) is None


def test_canonical_round_is_the_calendar_collection_round():
    inception = ppp.canonical_round(ppp.date(2021, 10, 1), ppp.date(2021, 12, 31))
    later_inception = ppp.canonical_round(ppp.date(2021, 10, 1), ppp.date(2022, 3, 31))
    assert inception[0] == later_inception[0] == "2022 Q1"
    assert later_inception[1:] == (ppp.date(2022, 1, 1), ppp.date(2022, 3, 31))
    september = ppp.canonical_round(ppp.date(2022, 4, 1), ppp.date(2022, 9, 30))
    assert september == ("2022 Q3", ppp.date(2022, 7, 1), ppp.date(2022, 9, 30))
    assert ppp.canonical_round(ppp.date(2022, 5, 1), ppp.date(2022, 10, 31))[0] == "2022 Q3"
    # Cumulative coverage from 2022 still belongs to the 2024 half-year it was filed in.
    first_half_2024 = ppp.canonical_round(ppp.date(2022, 4, 1), ppp.date(2024, 7, 31))
    assert first_half_2024 == ("Jan 2024 – Jun 2024", ppp.date(2024, 1, 1), ppp.date(2024, 6, 30))
    assert ppp.canonical_round(ppp.date(2024, 1, 1), ppp.date(2024, 12, 31))[0] == "Jul 2024 – Dec 2024"
    assert ppp.canonical_round(ppp.date(2022, 4, 1), ppp.date(2025, 3, 31))[0] == "Jan 2025 – Jun 2025"


def test_choose_submission_prefers_the_running_programme_total():
    calendar_year = {
        "status": "approved",
        "start": ppp.date(2024, 1, 1),
        "end": ppp.date(2024, 12, 31),
        "submitted_at": datetime(2025, 3, 1),
    }
    cumulative = {
        "status": "approved",
        "start": ppp.date(2022, 4, 1),
        "end": ppp.date(2024, 12, 31),
        "submitted_at": datetime(2025, 1, 1),
    }
    assert ppp.choose_submission(calendar_year, cumulative) is cumulative


def test_choose_submission_prefers_approved_over_later_on_hold():
    on_hold = {"status": "submitted", "submitted_at": datetime(2024, 2, 1)}
    approved = {"status": "approved", "submitted_at": datetime(2023, 1, 1)}
    assert ppp.choose_submission(on_hold, approved) is approved
    later = {"status": "approved", "submitted_at": datetime(2024, 5, 1)}
    assert ppp.choose_submission(approved, later) is later


def test_people_grid_collapses_to_one_indicator():
    survey = [
        _row("begin_group", "outcome", "Outcome indicators"),
        _row("select_one", "ind_1", "1.1 How many people were reached?", "a-na"),
        _row("integer", "total_1.1", "*Total*"),
        _row("note", "total_male_label", "*Total male: ${total_male_1.1}*"),
        _row("select_one", "agd_1.1", "Is your data disaggregated by sex and/or age?", "agd"),
        _row("begin_group", "gender_1.1", ""),
        _row("integer", "male_1.1", "*Male*"),
        _row("integer", "female_1.1", "*Female*"),
        _row("end_group", ""),
        _row("begin_group", "age_1.1", ""),
        _row("integer", "unknown_0-5_1.1", '<span style="display:none">unknown-0-5</span>'),
        _row("integer", "unknown_80_1.1", '<span style="display:none">unknown-80+</span>'),
        _row("end_group", ""),
        _row("begin_group", "sexage_1.1", ""),
        _row("integer", "male_0-5_1.1", '<span style="display:none">male-0-5</span>'),
        _row("integer", "female_80_1.1", '<span style="display:none">female-80+</span>'),
        _row("end_group", ""),
        _row("calculate", "cal_total_1.1", ""),
        _row("select_one", "act_1", "1.1 Communities are supported to prepare", "y-n"),
        _row("end_group", ""),
    ]
    sections = ppp.compile_survey(survey, [])
    assert [section["name"] for section in sections] == ["Outcome indicators"]
    fields = sections[0]["fields"]
    assert [field["kind"] for field in fields] == ["indicator", "question"]
    indicator, activity = fields
    assert indicator["label"].startswith("1.1 How many people")
    assert indicator["disagg"] is True
    assert indicator["binds"]["total"].endswith("total_1.1")
    assert indicator["binds"]["sex"]["male"].endswith("gender_1.1/male_1.1")
    assert indicator["binds"]["age"]["0-5"].endswith("unknown_0-5_1.1")
    assert indicator["binds"]["age"]["80+"].endswith("unknown_80_1.1")
    assert indicator["binds"]["sex_age"]["female"]["80+"].endswith("female_80_1.1")
    assert activity["qtype"] == "yesno"


def test_overview_note_becomes_sex_age_indicator_and_simple_counts_stay_questions():
    survey = [
        _row("begin_group", "country_overview_group", "Project Data overview"),
        _row("note", "unique_q", "How many unique individuals have been reached?"),
        _row("begin_group", "sexage", ""),
        _row("integer", "male_0-5", '<span style="display:none">male-0-5</span>'),
        _row("integer", "female_80", '<span style="display:none">female-80+</span>'),
        _row("end_group", ""),
        _row("integer", "unique_indiv_country_pop", "Local population"),
        _row("note", "disability_q", "How many people with disability has your National Society reached?"),
        _row("integer", "unique_indiv_country_disability_male", "Male"),
        _row("integer", "unique_indiv_country_disability_female", "Female"),
        _row("end_group", ""),
    ]
    fields = ppp.compile_survey(survey, [])[0]["fields"]
    assert [field["kind"] for field in fields] == ["indicator", "question", "indicator"]
    assert fields[0]["binds"]["sex_age"]["male"]["0-5"].endswith("sexage/male_0-5")
    assert fields[1]["qtype"] == "number"
    assert fields[1]["label"] == "Local population"
    assert fields[2]["binds"]["sex"]["female"].endswith("disability_female")


def test_applicable_gate_and_unlabeled_yesno_become_one_question():
    survey = [
        _row("select_one", "ind_5", "1.5 Does your National Society coordinate plans with authorities?", "a-na"),
        _row("select_one", "ind_5_yn", None, "y-n"),
    ]
    fields = ppp.compile_survey(survey, [])[0]["fields"]
    assert len(fields) == 1
    assert fields[0]["qtype"] == "yesno"
    assert fields[0]["allow_na"] is True
    assert fields[0]["binds"]["value"].endswith("ind_5_yn")
    assert ppp.scalar_answer({"ind_5": "not applicable", "ind_5_yn": "yes"}, fields[0]) == ppp.NOT_APPLICABLE
    assert ppp.scalar_answer({"ind_5": "applicable", "ind_5_yn": "yes"}, fields[0]) == "yes"


def test_close_indicator_bank_title_links_and_a_different_one_does_not():
    class Ind:
        def __init__(self, ident, name):
            self.id = ident
            self.name = name
            self.type = "number"
            self.unit = "People"
            self.archived = False
            self.name_translations = None
            self.aggregated_label = None
            self.monitoring_questions = None

    epidemic = Ind(1, "Number of people reached by epidemic and pandemic preparedness and response activities.")
    nutrition = Ind(2, "Number of people reached with messages on good nutrition and / or food preparation.")
    index = ppp.build_indicator_index([epidemic, nutrition])
    label = (
        "How many unique individuals your National Society has reached by epidemic "
        "and pandemic and preparedness response activities?"
    )
    assert ppp.match_indicator(label, numeric=True, disagg=True, index=index) is epidemic
    early_warning = "1.1 How many people have been reached by a functional early warning system?"
    assert ppp.match_indicator(early_warning, numeric=True, disagg=True, index=index) is None


def test_applicability_without_a_grid_stays_a_choice_question():
    survey = [
        _row("select_one a-na", "proportion", "4.1 What is the proportion of CVA expenditure?"),
        _row("integer", "expend_cva", "4.1.1 What is the total expenditure on CVA?"),
    ]
    fields = ppp.compile_survey(survey, [])[0]["fields"]
    assert [field["qtype"] for field in fields] == ["single_choice", "number"]
    assert fields[0]["options"] == ["applicable", "not applicable"]


def test_matrix_payload_honours_disaggregation_mode_and_not_applicable():
    binds = {
        "applicable": "group/ind",
        "agd": "group/agd",
        "total": "group/total",
        "sex": {"male": "group/gender/male", "female": "group/gender/female"},
        "age": {},
        "sex_age": {"male": {"0-5": "group/sexage/male_0-5"}},
    }
    assert ppp.matrix_payload({"group/ind": "not applicable", "group/total": 5}, binds) == {"not_applicable": True}
    sex = ppp.matrix_payload(
        {"group/ind": "applicable", "group/agd": "gender", "group/gender/male": "2", "group/gender/female": 3, "group/total": 9},
        binds,
    )
    assert sex == {"mode": "sex", "values": {"male": 2, "female": 3}}
    grid = ppp.matrix_payload({"group/agd": "genderage", "group/sexage/male_0-5": "4"}, binds)
    assert grid["mode"] == "sex_age"
    assert grid["values"] == {"male_0_5": 4}


def test_submission_time_is_naive_utc():
    parsed = ppp.submission_time({"_submission_time": "2022-03-09T10:56:02.939000+00:00"})
    assert parsed.tzinfo is None
    assert parsed == datetime(2022, 3, 9, 10, 56, 2, 939000)


def test_fold_name_matches_accented_country_names():
    assert ppp.fold_name("Côte d'Ivoire") == ppp.fold_name("Cote d'Ivoire")
    assert ppp.COUNTRY_ALIASES[ppp.fold_name("Palestinian territories")] == "palestine state of"
    assert ppp.COUNTRY_ALIASES[ppp.fold_name("Yemen, Rep.")] == "yemen"
