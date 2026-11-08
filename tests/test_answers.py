"""Scripted answers for repeatable runs (orchestrator/answers.py), with the fictional demo answers file."""

import json
from pathlib import Path

import pytest

from orchestrator.answers import FileAnswers, TerminalAnswers, load_answers

DEMO_ANSWERS = Path(__file__).resolve().parent.parent / "samples" / "demo" / "answers_demo.json"


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Does this apply to you: SQL?", True),
        ("Does this apply to you: PostgreSQL and REST API design?", True),
        ("Does this apply to you: At least 3 years of professional experience?", True),
        ("Does this apply to you: Docker and CI/CD?", True),
        ("Does this apply to you: Experience with AWS or Azure?", True),
        ("Does this apply to you: Occasional travel to customers (about 10%)?", True),
        ("Does this apply to you: Kubernetes?", False),  # no-rules win
        ("Does this apply to you: German (fluent)?", False),
        ("Does this apply to you: Experience with AWS?", False),  # nothing matches: otherwise = no
    ],
)
def test_demo_answers_match_by_words_not_ids(question, expected, capsys):
    assert FileAnswers(DEMO_ANSWERS).yes_no(question) is expected
    assert "(answers file)" in capsys.readouterr().out


def test_demo_answers_have_a_free_text_answer():
    assert "Lumenpath" in FileAnswers(DEMO_ANSWERS).free_text("Why this role?")


def test_matching_ignores_case(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"yes_no": {"yes_if_question_contains": ["python"], "otherwise": "no"}}))
    assert FileAnswers(path).yes_no("PYTHON?") is True


def test_missing_free_text_is_a_clear_error(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"yes_no": {"otherwise": "no"}}))
    with pytest.raises(ValueError, match="no free_text"):
        FileAnswers(path).free_text("Why this role?")


@pytest.mark.parametrize("content", ["not json", "{}", '{"yes_no": {"otherwise": "maybe"}}'])
def test_broken_files_are_rejected(tmp_path, content):
    path = tmp_path / "a.json"
    path.write_text(content)
    with pytest.raises(ValueError):
        FileAnswers(path)


def test_no_file_means_the_terminal():
    assert isinstance(load_answers(None), TerminalAnswers)
