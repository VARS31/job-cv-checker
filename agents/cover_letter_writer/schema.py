"""The Cover Letter Writer's data: the model's JSON schema, the model input,
the claims check and the style check (all plain Python except the schema)."""

import re

from agents.cv_text import quote_in_text

NOT_STATED = "not_stated"
CV, FROM_USER = "cv", "from_user"

# JSON OUTPUT ENFORCED: Ollama forces the model's answer into this shape.
LETTER_SCHEMA = {
    "type": "object",
    "properties": {
        "letter": {"type": "string", "description": "The full cover letter text."},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "A factual statement about the candidate."},
                    "source": {"type": "string", "enum": [CV, FROM_USER]},
                    "quote": {"type": "string", "description": "Exact supporting words."},
                },
                "required": ["claim", "source", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["letter", "claims"],
    "additionalProperties": False,
}


def build_question(requirements: dict) -> str:
    company = requirements.get("company", NOT_STATED)
    at_company = f" at {company}" if company != NOT_STATED else ""
    return f"In one or two sentences: why do you want this role{at_company}?"


def build_model_input(requirements: dict, report: dict, answer: str, cv_text: str) -> str:
    """Everything the model may use. Missing and unclear items are NOT sent, so they can't be mentioned."""
    matched = sorted(report.get("matched", []), key=lambda i: i["kind"] != "required")
    lines = [
        "JOB",
        f"Title: {requirements.get('job_title', NOT_STATED)}",
        f"Company: {requirements.get('company', NOT_STATED)}",
        "Responsibilities:",
        *[f"- {r}" for r in requirements.get("responsibilities", [])],
        "",
        "MATCHED REQUIREMENTS (with proof from the CV), required first:",
        *[f"- [{i['kind']}] {i['item']}: CV says \"{i['quote']}\"" for i in matched],
        "",
        "CONFIRMED BY THE CANDIDATE (true, but not in the CV):",
        *([f"- {i['item']}" for i in report.get("confirmed_by_user", [])] or ["- (none)"]),
        "",
        "CANDIDATE'S ANSWER (why this role at this company):",
        answer,
        "",
        "CV TEXT:",
        cv_text,
    ]
    return "\n".join(lines)


def build_rewrite_input(model_input: str, letter: str, unproven: list[dict]) -> str:
    """REWRITE: same input, plus the first letter and the claims that must go."""
    claims = "\n".join(f"- {c['claim']}" for c in unproven)
    return (
        f"{model_input}\n\n"
        "PREVIOUS LETTER:\n"
        f"{letter}\n\n"
        "These claims in the previous letter have NO valid proof. Rewrite the letter WITHOUT them, "
        "keep everything else that is proven, keep the same structure and rules, "
        f"and list the claims of the new letter:\n{claims}"
    )


def check_claims(claims: list[dict], cv_text: str, answer: str, report: dict) -> tuple[list[dict], list[dict]]:
    """CLAIMS CHECKED: every quote must really appear in its source. Returns (proven, unproven)."""
    user_text = "\n".join([answer, *[i["item"] for i in report.get("confirmed_by_user", [])]])
    proven, unproven = [], []
    for claim in claims:
        source_text = cv_text if claim["source"] == CV else user_text
        if quote_in_text(claim["quote"], source_text):
            proven.append(claim)
        else:
            where = "the CV" if claim["source"] == CV else "your answer or a confirmed item"
            unproven.append({**claim, "problem": f"quote not found in {where}"})
    return proven, unproven


# Style check (plain Python): words and phrases that make a letter sound machine-written.
BANNED_PHRASES = [
    "thrilled", "excited", "passionate", "passion", "leverage", "synergy", "synergies",
    "fast-paced", "in today's", "cutting-edge", "dynamic", "seamless", "seamlessly",
    "spearhead", "delve", "game-changer", "i am writing to express",
]
MIN_WORDS, MAX_WORDS = 250, 350
MIN_PARAGRAPH_WORDS = 25  # shorter blocks are the greeting, closing line or sign-off


SENTENCE_OPENER = r"(?=(?:I|It|This|That|These|Those|We|My|Our|There|Here)\b)"


def fix_dashes(letter: str) -> str:
    """Replace em-/en-dashes used as pauses with a comma; keep ranges like 2018–2023.

    "solutions—from RAG to agents—aligns" becomes "solutions, from RAG to agents, aligns".
    A dash at the end of a sentence becomes a full stop.
    """
    dash = r"(?<=\S)[ \t]*[—–][ \t]*(?=\S)"
    letter = re.sub(r"(?<=\d)[ \t]*[—–][ \t]*(?=\d)", "\x00", letter)  # protect number ranges
    # Before a typical sentence opener, the dash ends a sentence: "done — This was" -> "done. This was".
    letter = re.sub(dash + SENTENCE_OPENER, ". ", letter)
    letter = re.sub(dash, ", ", letter)
    letter = re.sub(r",\s*([,.;:!?])", r"\1", letter)  # no ", ," or ",."
    return letter.replace("\x00", "–")


def body_paragraphs(letter: str) -> list[str]:
    """Blocks separated by empty lines that are long enough to be body paragraphs."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", letter) if b.strip()]
    return [b for b in blocks if len(b.split()) >= MIN_PARAGRAPH_WORDS]


def style_warnings(letter: str, claims: list[dict]) -> list[str]:
    warnings = []
    if "—" in letter or " – " in letter or " - " in letter:
        warnings.append("Contains a dash used as a pause (em-dash or spaced dash).")
    lower = letter.lower()
    found = [p for p in BANNED_PHRASES if re.search(rf"\b{re.escape(p)}\b", lower)]
    if found:
        warnings.append(f"AI-sounding words: {', '.join(found)}.")
    if re.search(r"^\s*([-*•]|\d+\.)\s", letter, re.MULTILINE):
        warnings.append("Contains bullet points or a numbered list.")
    if re.search(r"\*[^*\n]+\*|^#", letter, re.MULTILINE):
        warnings.append("Contains Markdown formatting (* or #).")
    words = len(letter.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        warnings.append(f"Length is {words} words (target {MIN_WORDS} to {MAX_WORDS}).")
    paragraphs = len(body_paragraphs(letter))
    if paragraphs != 3:
        warnings.append(f"Has {paragraphs} body paragraphs (expected exactly 3).")
    if not claims:
        warnings.append("The model listed no claims, so nothing in the letter could be checked.")
    return warnings
