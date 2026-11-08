"""The Application Reviewer's grounding check, cliché net and review.md (plain Python)."""

from agents.application_reviewer.schema import (
    add_known_cliches,
    build_review_md,
    ground_review,
    letter_sentences,
)

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
