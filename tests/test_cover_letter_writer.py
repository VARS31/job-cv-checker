"""The Cover Letter Writer's plain-Python checks: dashes, claims, style, model input."""

from agents.cover_letter_writer.schema import (
    body_paragraphs,
    build_model_input,
    build_question,
    check_claims,
    fix_dashes,
    style_warnings,
)


def test_dashes_used_as_pauses_become_commas():
    assert fix_dashes("solutions—from RAG to agents—aligns") == "solutions, from RAG to agents, aligns"


def test_dash_before_a_sentence_opener_ends_the_sentence():
    assert fix_dashes("done — This was") == "done. This was"


def test_number_ranges_keep_their_dash():
    assert fix_dashes("2018–2023") == "2018–2023"


def test_claims_must_quote_their_source():
    claims = [
        {"claim": "uses Python", "source": "cv", "quote": "Python every day"},
        {"claim": "likes logistics", "source": "from_user", "quote": "I like logistics"},
        {"claim": "confirmed SQL", "source": "from_user", "quote": "SQL"},
        {"claim": "Kubernetes", "source": "cv", "quote": "Kubernetes expert"},
        {"claim": "wrong source", "source": "from_user", "quote": "Python every day"},
    ]
    report = {"confirmed_by_user": [{"item": "SQL", "kind": "required"}]}
    proven, unproven = check_claims(claims, "I use Python every day.", "I like logistics.", report)
    assert [c["claim"] for c in proven] == ["uses Python", "likes logistics", "confirmed SQL"]
    assert [c["claim"] for c in unproven] == ["Kubernetes", "wrong source"]
    assert unproven[0]["problem"] == "quote not found in the CV"


def test_style_warnings_catch_dashes_buzzwords_lists_and_length():
    warnings = style_warnings("I am thrilled - truly.\n- a bullet", [])
    text = " ".join(warnings)
    assert "dash" in text
    assert "AI-sounding words: thrilled" in text
    assert "bullet points" in text
    assert "Length is" in text
    assert "listed no claims" in text


def test_body_paragraphs_skip_greeting_and_sign_off():
    paragraph = " ".join(["word"] * 30)
    letter = f"Dear team,\n\n{paragraph}\n\n{paragraph}\n\nBest regards,\nJordan"
    assert len(body_paragraphs(letter)) == 2


def test_question_names_the_company_when_known():
    assert build_question({"company": "Example GmbH"}).endswith("at Example GmbH?")
    assert build_question({"company": "not_stated"}).endswith("this role?")


def test_model_input_leaves_out_missing_and_unclear_items():
    report = {
        "matched": [{"item": "Python", "kind": "required", "quote": "Python"}],
        "confirmed_by_user": [],
        "missing": [{"item": "Kubernetes", "kind": "required"}],
        "unclear": [{"item": "Go", "kind": "required", "note": ""}],
    }
    text = build_model_input({"job_title": "Dev", "company": "X"}, report, "answer", "cv text")
    assert "Python" in text
    assert "Kubernetes" not in text and "Go" not in text
