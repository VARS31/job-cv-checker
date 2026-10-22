"""The Application Reviewer's data: the model's JSON schema, the model input,
the grounding check, and the readable review.md (all plain Python except the schema)."""

import re

from agents.cv_text import quote_in_text

NOT_STATED = "not_stated"
MIN_PARAGRAPH_WORDS = 25  # shorter blocks are the greeting, closing line or sign-off


def _sentence_list(description: str) -> dict:
    return {
        "type": "array",
        "description": description,
        "items": {
            "type": "object",
            "properties": {
                "sentence": {"type": "string", "description": "Copied exactly from the letter."},
                "why": {"type": "string"},
            },
            "required": ["sentence", "why"],
            "additionalProperties": False,
        },
    }


# JSON OUTPUT ENFORCED: Ollama forces the model's answer into this shape.
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["shortlist", "maybe", "reject"]},
                "reason": {"type": "string", "description": "One sentence."},
            },
            "required": ["decision", "reason"],
            "additionalProperties": False,
        },
        "top_weaknesses": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "weakness": {"type": "string"},
                    "requirement": {"type": "string", "description": "The related job requirement."},
                },
                "required": ["weakness", "requirement"],
                "additionalProperties": False,
            },
        },
        "overclaims": _sentence_list("Letter sentences that claim more than the CV and report support."),
        "generic_phrases": _sentence_list("Letter sentences that are filler or sound AI-written."),
        "company_specificity": {
            "type": "object",
            "properties": {
                "specific": {"type": "boolean"},
                "explanation": {"type": "string", "description": "One sentence."},
            },
            "required": ["specific", "explanation"],
            "additionalProperties": False,
        },
        "interview_questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string"},
        },
    },
    "required": [
        "verdict", "top_weaknesses", "overclaims", "generic_phrases",
        "company_specificity", "interview_questions",
    ],
    "additionalProperties": False,
}


def body_paragraphs(letter: str) -> list[str]:
    """Blocks separated by empty lines that are long enough to be body paragraphs."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", letter) if b.strip()]
    return [b for b in blocks if len(b.split()) >= MIN_PARAGRAPH_WORDS]


def letter_sentences(letter: str) -> list[str]:
    """Split the letter's body paragraphs into sentences, so the model can judge each one."""
    sentences = []
    for paragraph in body_paragraphs(letter):
        sentences += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", paragraph) if s.strip()]
    return sentences


def build_model_input(requirements: dict, report: dict, letter: str, cv_text: str) -> str:
    def items(key: str, with_quote: bool = False) -> list[str]:
        return [
            f"- [{i['kind']}] {i['item']}" + (f": CV says \"{i['quote']}\"" if with_quote else "")
            for i in report.get(key, [])
        ] or ["- (none)"]

    paragraphs = body_paragraphs(letter)
    paragraph_3 = paragraphs[2] if len(paragraphs) >= 3 else "(the letter has no third body paragraph)"
    lines = [
        "JOB",
        f"Title: {requirements.get('job_title', NOT_STATED)}",
        f"Company: {requirements.get('company', NOT_STATED)}",
        "Required hard skills: " + ", ".join(requirements.get("hard_skills_required", [])),
        "Experience asked for: " + "; ".join(requirements.get("experience_details", [])),
        "Responsibilities:",
        *[f"- {r}" for r in requirements.get("responsibilities", [])],
        "",
        "CV MATCHER REPORT",
        f"Summary: {report.get('summary', '')}",
        "Matched (with CV proof):", *items("matched", with_quote=True),
        "Confirmed by the candidate (not in the CV):", *items("confirmed_by_user"),
        "MISSING:", *items("missing"),
        "UNCLEAR:", *items("unclear"),
        "",
        "COVER LETTER",
        letter,
        "",
        "LETTER SENTENCES (judge EVERY one for overclaims and generic phrases)",
        *[f"S{n}: {sentence}" for n, sentence in enumerate(letter_sentences(letter), start=1)],
        "",
        "THIRD BODY PARAGRAPH (for company_specificity)",
        paragraph_3,
        "",
        "CV TEXT",
        cv_text,
    ]
    return "\n".join(lines)


def ground_review(review: dict, letter: str) -> dict:
    """GROUNDING CHECK: keep only quoted sentences that really exist in the letter; count the rest."""
    dropped = {}
    for key in ("overclaims", "generic_phrases"):
        kept = [item for item in review[key] if quote_in_text(item["sentence"], letter)]
        dropped[key] = len(review[key]) - len(kept)
        review[key] = kept
    review["dropped_ungrounded"] = dropped
    # The model sometimes copies the "[required] " label from the input; remove it.
    for weakness in review["top_weaknesses"]:
        weakness["requirement"] = re.sub(r"^\[(required|preferred)\]\s*", "", weakness["requirement"])
    return review


# Known clichés, checked in plain Python in every letter sentence (lower case).
KNOWN_CLICHES = [
    "perfect fit", "ideal candidate", "i thrive", "thrive in", "leave my footprint",
    "aligns with my capabilities", "passionate about", "thrilled", "excited to",
    "fast-paced", "dynamic environment", "team player", "hit the ground running",
    "think outside the box", "go above and beyond", "unique opportunity", "make a difference",
]


def add_known_cliches(review: dict, letter: str) -> dict:
    """CLICHÉ CHECK: add letter sentences with a known cliché the model didn't list."""
    listed = {item["sentence"].strip() for item in review["generic_phrases"]}
    added = 0
    for sentence in letter_sentences(letter):
        found = [c for c in KNOWN_CLICHES if c in sentence.lower()]
        if found and sentence not in listed:
            review["generic_phrases"].append({"sentence": sentence, "why": f"known cliché: \"{found[0]}\""})
            added += 1
    review["added_by_cliche_check"] = added
    return review


def build_review_md(review: dict, requirements: dict, agent_version: str, model: str) -> str:
    """The readable version of the review, built in plain Python from the data."""
    verdict = review["verdict"]
    title = requirements.get("job_title", NOT_STATED)
    company = requirements.get("company", NOT_STATED)
    lines = [
        f"# Application review: {title}" + (f" at {company}" if company != NOT_STATED else ""),
        "",
        f"**Verdict: {verdict['decision']}.** {verdict['reason']}",
        "",
        "## Top weaknesses",
        *[f"{n}. {w['weakness']} *(requirement: {w['requirement']})*"
          for n, w in enumerate(review["top_weaknesses"], start=1)],
        "",
        "## Overclaims in the letter",
        *([f"- \"{o['sentence']}\"\n  {o['why']}" for o in review["overclaims"]] or ["None found."]),
        "",
        "## Generic or AI-sounding sentences",
        *([f"- \"{g['sentence']}\"\n  {g['why']}" for g in review["generic_phrases"]] or ["None found."]),
        "",
        "## Company specificity (paragraph 3)",
        ("Specific. " if review["company_specificity"]["specific"] else "Not specific. ")
        + review["company_specificity"]["explanation"],
        "",
        "## Likely interview questions",
        *[f"{n}. {q}" for n, q in enumerate(review["interview_questions"], start=1)],
        "",
    ]
    dropped = sum(review["dropped_ungrounded"].values())
    if dropped:
        lines += [f"*{dropped} item(s) were dropped because their quoted sentence is not in the letter.*", ""]
    lines.append(f"*Application Reviewer {agent_version}, model {model}.*")
    return "\n".join(lines) + "\n"
