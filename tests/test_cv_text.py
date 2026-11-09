"""The shared quote check and PDF reading (agents/cv_text.py)."""

from pathlib import Path

import pytest

from agents.cv_text import extract_pdf_text, quote_in_text

DEMO_CV = Path(__file__).resolve().parent.parent / "samples" / "demo" / "cv_demo.pdf"


def test_quote_ignores_case_punctuation_and_brackets():
    assert quote_in_text("Microsoft Azure (App Service)", "Microsoft Azure (App Service, PostgreSQL)")
    assert quote_in_text("python, sql", "Languages: Python, SQL, basic TypeScript")


def test_quote_keeps_plus_and_hash():
    assert quote_in_text("C++ and C#", "Knows C++ and C# well")
    assert not quote_in_text("C++", "Knows C and C#")


def test_quote_needs_words_in_order_and_whole_words():
    assert not quote_in_text("SQL Python", "Python, SQL")
    assert not quote_in_text("Java", "JavaScript")


def test_empty_quote_never_matches():
    assert not quote_in_text("", "anything")
    assert not quote_in_text("  ...  ", "anything")


def test_demo_cv_is_readable():
    """The fictional demo CV (committed) must give text, or the demo can't run."""
    text = extract_pdf_text(DEMO_CV.read_bytes())
    assert "Jordan Example" in text
    assert "FastAPI and PostgreSQL" in text


def test_not_a_pdf_raises_value_error():
    with pytest.raises(ValueError):
        extract_pdf_text(b"this is not a pdf")


@pytest.mark.parametrize(
    "filename, name",
    [("cv_jane_doe.pdf", "Jane Doe"), ("cv_robin_sample.pdf", "Robin Sample"),
     ("cv_casey_placeholder.pdf", "Casey Placeholder")],
)
def test_dummy_cvs_are_readable_and_marked_fictional(filename, name):
    text = extract_pdf_text((DEMO_CV.parent / filename).read_bytes())
    assert text.startswith(name)
    assert "Fictional demo CV" in text
