"""The CV Matcher's checklist, quote check, questions, answers and score (plain Python, no model)."""

from agents.cv_matcher.schema import (
    MAX_QUESTIONS,
    apply_model_checks,
    build_checklist,
    build_questions,
    cannot_show_in_cv,
    merge_answers,
)
from agents.cv_matcher.scoring import build_report, calculate_score

REQUIREMENTS = {
    "job_title": "Developer",
    "company": "Example GmbH",
    "hard_skills_required": ["Python", "SQL", "Go"],
    "education_required": "not_stated",
    "min_years_experience": 3,
    "experience_details": [],
    "languages": [{"language": "German", "level": "fluent", "required": False}],
    "other_requirements": [],
    "hard_skills_preferred": ["Docker"],
    "education_preferred": "not_stated",
    "soft_skills": [],
}
CV = "I write Python and SQL every day. Docker too."


def test_checklist_marks_required_and_preferred():
    checklist = build_checklist(REQUIREMENTS)
    assert [(i["text"], i["kind"]) for i in checklist] == [
        ("Python", "required"),
        ("SQL", "required"),
        ("Go", "required"),
        ("At least 3 years of professional experience", "required"),
        ("German (fluent)", "preferred"),
        ("Docker", "preferred"),
    ]


def analysis_with_model_answers():
    checklist = build_checklist(REQUIREMENTS)
    checks = [
        {"id": "r1", "status": "found", "quote": "write Python"},
        {"id": "r2", "status": "found", "quote": "an invented quote"},  # not in the CV
        {"id": "r3", "status": "missing", "quote": ""},
        {"id": "r4", "status": "unclear", "quote": ""},
        # r5 (German) left out: the model gave no answer
        {"id": "r6", "status": "found", "quote": "Docker too"},
    ]
    return apply_model_checks(checklist, checks, CV)


def test_found_without_a_real_quote_becomes_unclear():
    analysis = {i["id"]: i for i in analysis_with_model_answers()}
    assert analysis["r1"]["status"] == "found"
    assert analysis["r2"]["status"] == "unclear"
    assert "quote not found" in analysis["r2"]["note"]
    assert analysis["r5"]["status"] == "unclear"
    assert analysis["r5"]["note"] == "model gave no answer for this item"


def test_questions_only_for_unclear_required_items_experience_first():
    questions = build_questions(analysis_with_model_answers())
    assert [q["item_id"] for q in questions] == ["r4", "r2"]  # years first, then hard skills
    assert [q["id"] for q in questions] == ["q1", "q2"]


def test_at_most_five_questions():
    checklist = build_checklist({**REQUIREMENTS, "hard_skills_required": [f"skill {n}" for n in range(8)]})
    analysis = apply_model_checks(checklist, [], CV)  # no answers: everything unclear
    assert len(build_questions(analysis)) == MAX_QUESTIONS


def test_answers_yes_confirms_no_marks_missing():
    analysis = analysis_with_model_answers()
    questions = build_questions(analysis)
    analysis = {i["id"]: i for i in merge_answers(analysis, questions, {"q1": True, "q2": False})}
    assert analysis["r4"]["status"] == "confirmed"
    assert analysis["r2"]["status"] == "missing"


def test_score_counts_found_and_confirmed_with_weights():
    analysis = analysis_with_model_answers()
    analysis = merge_answers(analysis, build_questions(analysis), {"q1": True, "q2": False})
    # Matched: Python (2) + years confirmed (2) + Docker (1) = 5. Total: 4 required x 2 + 2 preferred x 1 = 10.
    assert calculate_score(analysis) == {"score_percent": 50, "points": 5, "max_points": 10}


def test_report_lists_each_status_and_a_summary():
    analysis = analysis_with_model_answers()
    analysis = merge_answers(analysis, build_questions(analysis), {"q1": True, "q2": False})
    report = build_report(REQUIREMENTS, analysis)
    assert [i["item"] for i in report["matched"]] == ["Python", "Docker"]
    assert [i["item"] for i in report["confirmed_by_user"]] == ["At least 3 years of professional experience"]
    assert [i["item"] for i in report["missing"]] == ["SQL", "Go"]
    assert [i["item"] for i in report["unclear"]] == ["German (fluent)"]
    assert report["summary"].startswith("The CV matches 50% of the requirements for Developer at Example GmbH.")



def test_new_preferred_fields_score_one_point_each():
    requirements = {
        **REQUIREMENTS,
        "experience_preferred": ["Logistics experience"],
        "other_requirements_preferred": ["Cloud certification"],
    }
    checklist = build_checklist(requirements)
    added = [i for i in checklist if i["source"] in ("experience_preferred", "other_requirements_preferred")]
    assert [(i["text"], i["kind"]) for i in added] == [
        ("Logistics experience", "preferred"), ("Cloud certification", "preferred"),
    ]
    analysis = apply_model_checks(checklist, [], CV)
    assert calculate_score(analysis)["max_points"] == 4 * 2 + 4 * 1


def test_what_a_cv_cannot_show_is_recognised():
    for text in ["Occasional travel to customers (about 10%)", "Willingness to relocate to Hamburg",
                 "Start date within 3 months", "Availability on Friday and Saturday nights",
                 "Willingness to work three shifts, including weekends"]:
        assert cannot_show_in_cv(text), text
    for text in ["Python", "High availability systems", "Kubernetes", "PostgreSQL"]:
        assert not cannot_show_in_cv(text), text


def test_cannot_show_items_are_unclear_never_missing_and_asked_first():
    requirements = {
        **REQUIREMENTS,
        "other_requirements": ["Occasional travel to customers (about 10%)"],
        "other_requirements_preferred": ["Willingness to relocate"],
    }
    checklist = build_checklist(requirements)
    by_text = {i["text"]: i["id"] for i in checklist}
    checks = [{"id": i["id"], "status": "missing", "quote": ""} for i in checklist]
    analysis = {i["text"]: i for i in apply_model_checks(checklist, checks, CV)}
    travel, relocate = analysis["Occasional travel to customers (about 10%)"], analysis["Willingness to relocate"]
    assert travel["status"] == relocate["status"] == "unclear"
    assert "can't show" in travel["note"]
    assert analysis["Go"]["status"] == "missing"  # an ordinary skill stays missing

    questions = build_questions(list(analysis.values()))
    asked = [q["item_id"] for q in questions]
    # Both are asked (the preferred one too), and before anything else.
    assert asked[:2] == [by_text["Occasional travel to customers (about 10%)"], by_text["Willingness to relocate"]]


def test_a_cannot_show_item_found_with_a_real_quote_stays_found():
    checklist = build_checklist({**REQUIREMENTS, "other_requirements": ["Willing to travel"]})
    item = next(i for i in checklist if i["text"] == "Willing to travel")
    analysis = apply_model_checks(checklist, [{"id": item["id"], "status": "found", "quote": "Docker too"}], CV)
    assert next(i for i in analysis if i["id"] == item["id"])["status"] == "found"
