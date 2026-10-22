"""PIPELINE STEPS: the fixed order of agents, what each one receives, and what it returns.

To add an agent (e.g. an Application Reviewer): write one more Step and append it to STEPS.
Nothing else in the orchestrator needs to change.
"""

from dataclasses import dataclass
from typing import Callable

from a2a.helpers import get_data_parts, get_text_parts, new_data_part, new_raw_part, new_text_part
from a2a.types import Artifact, Part


@dataclass(frozen=True)
class Step:
    name: str  # shown in progress lines, e.g. "CV Matcher"
    url_setting: str  # .env setting with the agent's URL
    default_url: str  # used when the setting is missing
    start_command: str  # shown when the agent is not reachable
    # Results so far (job ad, CV, earlier artifacts) -> the parts of the message to send.
    build_parts: Callable[[dict], list[Part]]
    # The agent's artifacts -> new results, added to the results for the next steps.
    read_artifacts: Callable[[list[Artifact]], dict]
    # Result key -> file name in results/runs/<date-time>/ (dict/list as JSON, text as is).
    outputs: dict[str, str]


def _cv_part(results: dict) -> Part:
    # FILE PART: the CV as raw bytes.
    return new_raw_part(results["cv_pdf"], media_type="application/pdf", filename=results["cv_filename"])


def _data(results: dict, key: str) -> Part:
    # DATA PART: an earlier agent's JSON result, passed on unchanged.
    return new_data_part(results[key], media_type="application/json")


def _first_data(artifacts: list[Artifact]) -> dict:
    data = [d for a in artifacts for d in get_data_parts(a.parts)]
    if not data:
        raise ValueError("the agent's artifact has no data part")
    return data[0]


def _letter(artifacts: list[Artifact]) -> dict:
    texts = [t for a in artifacts for t in get_text_parts(a.parts)]
    if not texts:
        raise ValueError("the agent's artifact has no text part")
    return {"cover_letter": texts[0], "letter_details": _first_data(artifacts)}


JOB_ANALYST = Step(
    name="Job Analyst",
    url_setting="JOB_ANALYST_URL",
    default_url="http://localhost:9001",
    start_command="python -m agents.job_analyst",
    build_parts=lambda r: [new_text_part(r["job_ad"])],
    read_artifacts=lambda artifacts: {"requirements": _first_data(artifacts)},
    outputs={"requirements": "requirements.json"},
)

CV_MATCHER = Step(
    name="CV Matcher",
    url_setting="CV_MATCHER_URL",
    default_url="http://localhost:9002",
    start_command="python -m agents.cv_matcher",
    build_parts=lambda r: [_data(r, "requirements"), _cv_part(r)],
    read_artifacts=lambda artifacts: {"match_report": _first_data(artifacts)},
    outputs={"match_report": "match_report.json"},
)

COVER_LETTER_WRITER = Step(
    name="Cover Letter Writer",
    url_setting="COVER_LETTER_URL",
    default_url="http://localhost:9003",
    start_command="python -m agents.cover_letter_writer",
    build_parts=lambda r: [_data(r, "requirements"), _data(r, "match_report"), _cv_part(r)],
    read_artifacts=_letter,
    outputs={"cover_letter": "cover_letter.md", "letter_details": "claims.json"},
)

# Fixed routing: always this order.
STEPS = [JOB_ANALYST, CV_MATCHER, COVER_LETTER_WRITER]
