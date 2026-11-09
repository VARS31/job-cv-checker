"""The Application Reviewer's grounding check, cliché net and review.md (plain Python)."""

from agents.application_reviewer.__main__ import split_inputs
from agents.application_reviewer.schema import (
    add_known_cliches,
    build_model_input,
    build_review_md,
    ground_review,
    letter_sentences,
)
from orchestrator.pipeline import labelled_text

PARAGRAPH = (
    "I built a search assistant for support teams over many articles and measured answer quality "
    "with real questions. I am the perfect fit for this role and would bring the same care to your team."
)
LETTER = f"Dear team,\n\n{PARAGRAPH}\n\nBest regards,\nJordan"


def model_review() -> dict:
    return {
        "verdict": {"decision": "maybe", "reason": "Solid backend skills."},
        "top_weaknesses": [
            {"weakness": "No SQL shown", "requirement": "[required] SQL"},
            {"weakness": "w2", "requirement": "r2"},
            {"weakness": "w3", "requirement": "r3"},
        ],
        "overclaims": [
            {"sentence": "I led a team of fifty engineers.", "why": "not in the letter"},
            {"sentence": "I built a search assistant for support teams over many articles", "why": "x"},
        ],
        "generic_phrases": [],
        "company_specificity": {"specific": False, "explanation": "No company facts."},
        "interview_questions": ["q1", "q2", "q3"],
    }


def test_letter_is_split_into_body_sentences():
    assert len(letter_sentences(LETTER)) == 2


def test_quotes_not_in_the_letter_are_dropped_and_counted():
    review = ground_review(model_review(), LETTER)
    assert review["dropped_ungrounded"] == {"overclaims": 1, "generic_phrases": 0}
    assert len(review["overclaims"]) == 1


def test_copied_requirement_label_is_removed():
    review = ground_review(model_review(), LETTER)
    assert review["top_weaknesses"][0]["requirement"] == "SQL"


def test_known_cliches_are_added_once():
    review = add_known_cliches(ground_review(model_review(), LETTER), LETTER)
    assert review["added_by_cliche_check"] == 1
    assert "perfect fit" in review["generic_phrases"][0]["why"]
    again = add_known_cliches(review, LETTER)
    assert again["added_by_cliche_check"] == 0


def test_review_md_shows_verdict_and_dropped_count():
    review = add_known_cliches(ground_review(model_review(), LETTER), LETTER)
    md = build_review_md(review, {"job_title": "Dev", "company": "Example GmbH"}, "0.1.0", "some-model")
    assert md.startswith("# Application review: Dev at Example GmbH")
    assert "**Verdict: maybe.**" in md
    assert "1 item(s) were dropped" in md
    assert md.rstrip().endswith("*Application Reviewer 0.1.0, model some-model.*")


JOB_AD = "Backend Engineer at Example GmbH. About us: we build software for freight companies."


def test_reviewer_input_contains_the_original_job_ad():
    report = {"summary": "", "matched": [], "confirmed_by_user": [], "missing": [], "unclear": []}
    text = build_model_input({"job_title": "Backend Engineer"}, report, LETTER, "cv text", JOB_AD)
    assert "JOB AD (the original text, including the company description)" in text
    assert "software for freight companies" in text


def test_labelled_text_parts_tell_letter_and_job_ad_apart():
    from a2a.helpers import new_data_part

    parts = [
        new_data_part({"hard_skills_required": []}),
        new_data_part({"score_percent": 50}),
        labelled_text(JOB_AD, "job_ad"),  # order doesn't matter
        labelled_text(LETTER, "cover_letter"),
    ]
    requirements, report, letter, job_ad = split_inputs(parts)
    assert requirements is not None and report is not None
    assert letter == LETTER.strip() and job_ad == JOB_AD


def test_an_unlabelled_text_part_is_the_letter():
    from a2a.helpers import new_text_part

    _, _, letter, job_ad = split_inputs([new_text_part(LETTER)])
    assert letter == LETTER.strip() and job_ad is None
