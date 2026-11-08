"""The Job Analyst's clean-up after the model answers (agents/job_analyst/schema.py)."""

from agents.job_analyst.schema import REQUIREMENTS_SCHEMA, clean_requirements


def empty_requirements() -> dict:
    """An answer with every field present and empty, as the schema allows."""
    data = {
        name: ([] if spec.get("type") == "array" else "")
        for name, spec in REQUIREMENTS_SCHEMA["properties"].items()
    }
    data["min_years_experience"] = None
    return data


def test_schema_requires_every_field():
    assert set(REQUIREMENTS_SCHEMA["required"]) == set(REQUIREMENTS_SCHEMA["properties"])


def test_preferred_markers_move_items_out_of_required():
    data = empty_requirements()
    data["hard_skills_required"] = [
        "Python", "MEDDPICC (preferred)", "Docker is a plus", "Kubernetes nice to have", "Ideally Go",
    ]
    out = clean_requirements(data)
    assert out["hard_skills_required"] == ["Python"]
    assert out["hard_skills_preferred"] == ["MEDDPICC", "Docker", "Kubernetes", "Go"]


def test_duplicates_are_removed_within_and_across_fields():
    data = empty_requirements()
    data["hard_skills_required"] = ["Python", "python"]
    data["soft_skills"] = ["Python", "Teamwork"]
    out = clean_requirements(data)
    assert out["hard_skills_required"] == ["Python"]
    assert out["soft_skills"] == ["Teamwork"]


def test_languages_keep_one_entry_and_fill_missing_level():
    data = empty_requirements()
    data["languages"] = [
        {"language": "English", "level": "", "required": True},
        {"language": "english", "level": "C1", "required": True},
        {"language": "not_stated", "level": "", "required": False},
    ]
    out = clean_requirements(data)
    assert out["languages"] == [{"language": "English", "level": "not_stated", "required": True}]


def test_empty_text_fields_become_not_stated():
    out = clean_requirements(empty_requirements())
    assert out["job_title"] == "not_stated"
    assert out["seniority"] == "not_stated"


def test_items_equal_to_an_education_field_are_dropped():
    data = empty_requirements()
    data["education_required"] = "BSc Computer Science"
    data["experience_details"] = ["BSc Computer Science", "3+ years backend"]
    out = clean_requirements(data)
    assert out["experience_details"] == ["3+ years backend"]
