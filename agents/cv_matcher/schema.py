"""The CV Matcher's data: checklist from the job requirements, the model's JSON schema,
the quote check, the yes/no questions, and merging the user's answers."""

from agents.cv_text import quote_in_text

NOT_STATED = "not_stated"
REQUIRED, PREFERRED = "required", "preferred"
MAX_QUESTIONS = 5

# Status values. The model returns the first three; "confirmed" comes from the user.
FOUND, MISSING, UNCLEAR, CONFIRMED = "found", "missing", "unclear", "confirmed"


# JSON OUTPUT ENFORCED: Ollama forces the model's answer into this shape.
CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Requirement id, e.g. r3."},
                    "status": {"type": "string", "enum": [FOUND, MISSING, UNCLEAR]},
                    "quote": {"type": "string", "description": "Exact CV quote for found, else empty."},
                },
                "required": ["id", "status", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["checks"],
    "additionalProperties": False,
}


def build_checklist(req: dict) -> list[dict]:
    """Turn the Job Analyst's JSON into a flat list of items, each required or preferred."""
    items = []

    def add(text: str, kind: str, source: str) -> None:
        items.append({"id": f"r{len(items) + 1}", "text": text, "kind": kind, "source": source})

    for skill in req.get("hard_skills_required", []):
        add(skill, REQUIRED, "hard_skills_required")
    if req.get("education_required", NOT_STATED) != NOT_STATED:
        add(req["education_required"], REQUIRED, "education_required")
    if req.get("min_years_experience") is not None:
        add(f"At least {req['min_years_experience']:g} years of professional experience",
            REQUIRED, "min_years_experience")
    for point in req.get("experience_details", []):
        add(point, REQUIRED, "experience_details")
    for lang in req.get("languages", []):
        level = "" if lang["level"] == NOT_STATED else f" ({lang['level']})"
        add(f"{lang['language']}{level}", REQUIRED if lang["required"] else PREFERRED, "languages")
    for point in req.get("other_requirements", []):
        add(point, REQUIRED, "other_requirements")
    for skill in req.get("hard_skills_preferred", []):
        add(skill, PREFERRED, "hard_skills_preferred")
    if req.get("education_preferred", NOT_STATED) != NOT_STATED:
        add(req["education_preferred"], PREFERRED, "education_preferred")
    for skill in req.get("soft_skills", []):
        add(skill, PREFERRED, "soft_skills")  # hard to prove from a CV, so only weight 1
    return items


def checklist_as_text(checklist: list[dict]) -> str:
    """The checklist as the model sees it: 'r1 [required] Python'."""
    return "\n".join(f"{i['id']} [{i['kind']}] {i['text']}" for i in checklist)


def apply_model_checks(checklist: list[dict], checks: list[dict], cv_text: str) -> list[dict]:
    """Combine the checklist with the model's answer. A "found" needs a real quote."""
    by_id = {c["id"]: c for c in checks}
    analysis = []
    for item in checklist:
        check = by_id.get(item["id"])
        status, quote, note = UNCLEAR, "", ""
        if check is None:
            note = "model gave no answer for this item"
        else:
            status, quote = check["status"], check["quote"].strip()
            if status == FOUND and not quote:
                status, note = UNCLEAR, "model said found but gave no quote"
            elif status == FOUND and not quote_in_text(quote, cv_text):
                status, note = UNCLEAR, f"quote not found in CV: {quote!r}"
            if status != FOUND:
                quote = ""
        analysis.append({**item, "status": status, "quote": quote, "note": note})
    return analysis


# Question priority: years/experience first, then education, then required hard skills,
# then everything else (languages, other requirements).
QUESTION_PRIORITY = {
    "min_years_experience": 0,
    "experience_details": 0,
    "education_required": 1,
    "hard_skills_required": 2,
}


def build_questions(analysis: list[dict]) -> list[dict]:
    """Up to 5 yes/no questions, one per unclear REQUIRED item, most important first."""
    unclear = [i for i in analysis if i["kind"] == REQUIRED and i["status"] == UNCLEAR]
    # sorted() keeps the checklist order within each priority group.
    unclear = sorted(unclear, key=lambda i: QUESTION_PRIORITY.get(i["source"], 3))
    return [
        {"id": f"q{n}", "item_id": item["id"], "question": f"Does this apply to you: {item['text']}?"}
        for n, item in enumerate(unclear[:MAX_QUESTIONS], start=1)
    ]


def merge_answers(analysis: list[dict], questions: list[dict], answers: dict) -> list[dict]:
    """ANSWERS MERGED: yes -> confirmed (counts as matched), no -> missing, no answer -> unclear."""
    item_by_id = {i["id"]: i for i in analysis}
    for q in questions:
        answer = answers.get(q["id"])
        if answer is True:
            item_by_id[q["item_id"]].update(status=CONFIRMED, note="confirmed by the user")
        elif answer is False:
            item_by_id[q["item_id"]].update(status=MISSING, note="user said no")
    return analysis
