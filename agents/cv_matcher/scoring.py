"""Match score and final report, in plain Python (no model)."""

from agents.cv_matcher.schema import CONFIRMED, FOUND, MISSING, NOT_STATED, REQUIRED, UNCLEAR

WEIGHTS = {"required": 2, "preferred": 1}


def calculate_score(analysis: list[dict]) -> dict:
    """SCORE CALCULATED: matched weight / total weight, in %. Only found and confirmed count."""
    total = sum(WEIGHTS[i["kind"]] for i in analysis)
    matched = sum(WEIGHTS[i["kind"]] for i in analysis if i["status"] in (FOUND, CONFIRMED))
    percent = round(100 * matched / total) if total else 0
    return {"score_percent": percent, "points": matched, "max_points": total}


def _join(texts: list[str], limit: int = 3) -> str:
    shown = ", ".join(texts[:limit])
    return shown + (f" and {len(texts) - limit} more" if len(texts) > limit else "")


def _summary(requirements: dict, analysis: list[dict], score: dict) -> str:
    """3-4 plain sentences built from the results; nothing is invented."""
    title = requirements.get("job_title", "this job")
    company = requirements.get("company", NOT_STATED)
    role = f"{title} at {company}" if company != NOT_STATED else title

    required = [i for i in analysis if i["kind"] == REQUIRED]
    req_found = [i["text"] for i in required if i["status"] == FOUND]
    req_confirmed = [i["text"] for i in required if i["status"] == CONFIRMED]
    req_missing = [i["text"] for i in required if i["status"] in (MISSING, UNCLEAR)]

    sentences = [f"The CV matches {score['score_percent']}% of the requirements for {role}."]
    met = len(req_found) + len(req_confirmed)
    confirmed = f", {len(req_confirmed)} of them confirmed by you" if req_confirmed else ""
    verb = "is" if met == 1 else "are"
    sentences.append(f"{met} of {len(required)} required items {verb} met{confirmed}.")
    if req_found:
        sentences.append(f"Clear matches in the CV include {_join(req_found)}.")
    if req_missing:
        sentences.append(f"Required items not met: {_join(req_missing)}.")
    else:
        sentences.append("No required items are missing.")
    return " ".join(sentences)


def build_report(requirements: dict, analysis: list[dict]) -> dict:
    """The final artifact: score, matches with quotes, confirmed, missing, unclear, summary."""
    score = calculate_score(analysis)

    def items(status: str, with_quote: bool = False) -> list[dict]:
        return [
            {"item": i["text"], "kind": i["kind"], **({"quote": i["quote"]} if with_quote else {})}
            for i in analysis
            if i["status"] == status
        ]

    return {
        "job_title": requirements.get("job_title", NOT_STATED),
        "company": requirements.get("company", NOT_STATED),
        **score,
        "matched": items(FOUND, with_quote=True),
        "confirmed_by_user": items(CONFIRMED),
        "missing": items(MISSING),
        # Unclear items count as not matched (e.g. preferred items, or questions beyond 5).
        "unclear": [{"item": i["text"], "kind": i["kind"], "note": i["note"]}
                    for i in analysis if i["status"] == UNCLEAR],
        "summary": _summary(requirements, analysis, score),
    }
