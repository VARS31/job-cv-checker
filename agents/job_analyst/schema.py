"""The Job Analyst's output contract: the JSON schema, plus clean-up after the model answers."""

import re

NOT_STATED = "not_stated"

# Words that mean "preferred". An item in a required list containing one of these
# is moved to the matching preferred list, and the marker is removed from its text.
PREFERRED_MARKER = re.compile(
    r"\(\s*preferred\s*\)|\b(?:is\s+)?a\s+plus\b|\bnice[\s-]to[\s-]have\b|\bideally\b",
    re.IGNORECASE,
)
# Required list -> matching preferred list.
REQUIRED_TO_PREFERRED = {"hard_skills_required": "hard_skills_preferred"}


def _text(description: str) -> dict:
    return {"type": "string", "description": description}


def _list(description: str, max_items: int | None = None) -> dict:
    schema = {"type": "array", "items": {"type": "string"}, "description": description}
    if max_items is not None:
        schema["maxItems"] = max_items
    return schema


# JSON OUTPUT ENFORCED: Ollama forces the model's answer into this shape.
# Note: Ollama uses the schema to restrict the output; the model does not read
# the descriptions. The model's real instructions are in prompts/job_analyst.md.
REQUIREMENTS_SCHEMA = {
    "type": "object",
    "properties": {
        "job_title": _text("The job title as written in the ad."),
        "company": _text("The hiring company's name, or not_stated."),
        "seniority": {
            "type": "string",
            "enum": ["junior", "mid", "senior", "lead", "principal", NOT_STATED],
            "description": "Seniority only if the ad's wording says it, else not_stated.",
        },
        "location": _text("City/country as written, or not_stated."),
        "remote_policy": {
            "type": "string",
            "enum": ["on-site", "hybrid", "remote", NOT_STATED],
            "description": "Work-place policy only if the ad says it, else not_stated.",
        },
        "education_required": _text("Required degree as written, or not_stated."),
        "education_preferred": _text("Degree the ad calls preferred/ideal, or not_stated."),
        "min_years_experience": {
            "type": ["number", "null"],
            "description": "The main minimum years of experience, or null.",
        },
        "experience_details": _list("Short points on specific experience asked for, e.g. '3+ years AI solutions'."),
        "hard_skills_required": _list("Required learnable, checkable skills as short items."),
        "hard_skills_preferred": _list("Hard skills the ad calls a plus/preferred, as short items."),
        "soft_skills": _list("Personal and people skills as short items."),
        "languages": {
            "type": "array",
            "description": "Spoken languages with level and whether they are required.",
            "items": {
                "type": "object",
                "properties": {
                    "language": _text("Language name, e.g. English."),
                    "level": _text("Level as written, e.g. fluent, or not_stated."),
                    "required": {"type": "boolean", "description": "True if required, false if a plus."},
                },
                "required": ["language", "level", "required"],
                "additionalProperties": False,
            },
        },
        "responsibilities": _list("0 to 6 short points on what the job involves.", max_items=6),
        "other_requirements": _list("Anything else asked for: travel, certifications, permits."),
    },
    "additionalProperties": False,
}
REQUIREMENTS_SCHEMA["required"] = list(REQUIREMENTS_SCHEMA["properties"])

TEXT_FIELDS = [
    "job_title", "company", "seniority", "location", "remote_policy",
    "education_required", "education_preferred",
]
# Order matters for de-duplication across fields: the first field keeps the item.
LIST_FIELDS = [
    "hard_skills_required", "hard_skills_preferred", "soft_skills",
    "experience_details", "other_requirements", "responsibilities",
]


def _remove_marker(item: str) -> str:
    """'MEDDPICC (preferred)' -> 'MEDDPICC'; 'Docker is a plus' -> 'Docker'."""
    item = PREFERRED_MARKER.sub("", item)
    item = re.sub(r"\(\s*\)", "", item)  # empty brackets left behind
    return re.sub(r"\s+", " ", item).strip(" ,;:-")


def clean_requirements(data: dict) -> dict:
    """Fix required/preferred markers, trim spaces, remove duplicates (plain Python, no model)."""
    # Items marked as preferred move out of the required list.
    for required, preferred in REQUIRED_TO_PREFERRED.items():
        keep = []
        for item in data[required]:
            if PREFERRED_MARKER.search(item):
                data[preferred].append(_remove_marker(item))
            else:
                keep.append(item)
        data[required] = keep

    for field in TEXT_FIELDS:
        data[field] = data[field].strip() or NOT_STATED

    # Languages: trim, drop placeholders like "not_stated", keep each language only once.
    seen = {"", NOT_STATED}
    languages = []
    for item in data["languages"]:
        item["language"] = item["language"].strip()
        item["level"] = item["level"].strip() or NOT_STATED
        key = item["language"].lower()
        if key not in seen:
            seen.add(key)
            languages.append(item)
    data["languages"] = languages

    # Lists: an item already used (in a language, an education field, or an
    # earlier list) is dropped. Comparison ignores upper/lower case.
    seen |= {data[f].lower() for f in ("education_required", "education_preferred")}
    for field in LIST_FIELDS:
        kept = []
        for item in data[field]:
            item = item.strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                kept.append(item)
        data[field] = kept
    return data
