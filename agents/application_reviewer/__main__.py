"""Application Reviewer agent: reviews a whole application like a senior recruiter.

It only reports (verdict, weaknesses, overclaims, generic phrases, interview questions);
it never rewrites the letter. No input-required.
Instructions (the rubric): prompts/application_reviewer.md. Schema and checks: schema.py.

Run with:  python -m agents.application_reviewer
"""

import json

import uvicorn
from starlette.applications import Starlette

from google.protobuf.json_format import MessageToDict

from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, UnsupportedOperationError

from agents.application_reviewer.schema import (
    REVIEW_SCHEMA,
    add_known_cliches,
    build_model_input,
    build_review_md,
    ground_review,
)
from agents.cv_text import extract_pdf_text
from agents.model_client import (
    PROJECT_ROOT,
    USAGE_KEY,
    ModelError,
    Usage,
    ask_model,
    read_setting,
    startup_check,
)

HOST = "localhost"
PORT = 9004
URL = f"http://{HOST}:{PORT}"

PROMPT_FILE = PROJECT_ROOT / "prompts" / "application_reviewer.md"
MODEL_TIMEOUT_SECONDS = 300


# AGENT CARD: the public "business card" other agents read to learn
# who this agent is, where to reach it, and what skills it has.
AGENT_CARD = AgentCard(
    name="Application Reviewer",
    description="Reviews a job application like a senior recruiter. Reports only; never rewrites the letter.",
    version="0.3.0",
    supported_interfaces=[
        AgentInterface(url=URL, protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    capabilities=AgentCapabilities(streaming=False),
    # Input: requirements + match report (data), the cover letter and the job ad (text), the CV (PDF file).
    default_input_modes=["application/json", "text/plain", "application/pdf"],
    # Output: the review as JSON, plus a readable Markdown version.
    default_output_modes=["application/json", "text/markdown"],
    skills=[
        AgentSkill(
            id="review_application",
            name="Review application",
            description=(
                "Gives a verdict (shortlist / maybe / reject) with a reason, the top 3 weaknesses, "
                "overclaims and generic sentences in the cover letter (each quoted exactly and "
                "checked against the letter), whether paragraph 3 is company-specific, and "
                "3 to 5 likely interview questions."
            ),
            tags=["review", "recruiter", "cover letter", "job application"],
            examples=["Requirements JSON + match report JSON + cover letter text + job ad text + cv.pdf"],
        )
    ],
)


def split_inputs(parts) -> tuple[dict | None, dict | None, str | None, str | None]:
    """Find the requirements and the report (data parts), the letter and the job ad (text parts).

    TEXT PART METADATA tells the two texts apart: {"content": "job_ad"} marks the ad;
    the letter is the text part marked {"content": "cover_letter"} (or the first unmarked one).
    """
    requirements = report = None
    for data in get_data_parts(parts):
        if isinstance(data, dict) and "score_percent" in data:
            report = data
        elif isinstance(data, dict) and "hard_skills_required" in data:
            requirements = data
    letter = job_ad = None
    for part in parts:
        if not part.HasField("text"):
            continue
        content = MessageToDict(part.metadata).get("content")
        if content == "job_ad":
            job_ad = part.text.strip()
        elif letter is None and content in (None, "cover_letter"):
            letter = part.text.strip()
    return requirements, report, letter, job_ad


class ApplicationReviewerExecutor(AgentExecutor):
    def __init__(self, model: str) -> None:
        self.model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # TASK: create it on the first (and only) message.
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        parts = context.message.parts
        # FILE PART: the CV. DATA PARTS: requirements and report. TEXT PART: the letter.
        pdf_parts = [p for p in parts if p.HasField("raw")]
        requirements, report, letter, job_ad = split_inputs(parts)
        if not pdf_parts or requirements is None or report is None or not letter or not job_ad:
            await self._fail(
                updater,
                "Expected two data parts (requirements, CV Matcher report), two text parts "
                "(the cover letter, and the job ad marked with metadata content=job_ad) "
                "and one file part (CV as PDF).",
            )
            return

        await updater.start_work()  # STATUS: working
        # USAGE: tokens, cost and time of this task's model call, sent back as result metadata.
        usage = Usage(self.model)
        try:
            cv_text = extract_pdf_text(pdf_parts[0].raw)
            review = await self._review(requirements, report, letter, cv_text, job_ad, usage, context.context_id)
        except (ModelError, ValueError) as error:
            await self._fail(updater, str(error), usage)
            return

        review["agent_version"] = AGENT_CARD.version
        review["model"] = self.model
        review_md = build_review_md(review, requirements, AGENT_CARD.version, self.model)

        # ARTIFACT: the review as a DATA part, and the readable review.md as a TEXT part.
        await updater.add_artifact(
            [
                new_data_part(review, media_type="application/json"),
                new_text_part(review_md, media_type="text/markdown"),
            ],
            name="application_review",
            # The artifact's METADATA says which model produced it and what it cost.
            metadata={USAGE_KEY: usage.as_metadata()},
        )
        await updater.complete()  # STATUS: completed

    async def _review(
        self, requirements: dict, report: dict, letter: str, cv_text: str, job_ad: str, usage: Usage, run_id: str
    ) -> dict:
        instructions = PROMPT_FILE.read_text(encoding="utf-8")
        # MODEL CALL (through the shared model client), schema-enforced, temperature 0 on Ollama.
        answer = await ask_model(
            build_model_input(requirements, report, letter, cv_text, job_ad),
            self.model,
            system=instructions,
            json_schema=REVIEW_SCHEMA,
            temperature=0.0,
            timeout=MODEL_TIMEOUT_SECONDS,
            usage=usage,
            run_id=run_id,
        )
        try:
            review = json.loads(answer)
        except json.JSONDecodeError as e:
            raise ValueError(f"The model's answer is not valid JSON: {answer[:200]!r}") from e
        # GROUNDING CHECK: drop quoted sentences that are not really in the letter.
        review = ground_review(review, letter)
        # CLICHÉ CHECK: plain-Python safety net for known clichés the model missed.
        return add_known_cliches(review, letter)

    async def _fail(self, updater: TaskUpdater, error: str, usage: Usage | None = None) -> None:
        # FAILED STATUS: final state, with the error as a text message (and the usage so far, if any).
        metadata = {USAGE_KEY: usage.as_metadata()} if usage else None
        await updater.failed(
            updater.new_agent_message([new_text_part(f"Application Reviewer failed: {error}")], metadata=metadata)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()


def main() -> None:
    # The model belongs to the agent: read once at startup, checked before the server starts.
    model = read_setting("REVIEWER_MODEL")
    startup_check("Application Reviewer", model)
    handler = DefaultRequestHandler(
        agent_executor=ApplicationReviewerExecutor(model),
        task_store=InMemoryTaskStore(),
        agent_card=AGENT_CARD,
    )
    routes = [
        # GET /.well-known/agent-card.json -> serves the AGENT CARD.
        *create_agent_card_routes(AGENT_CARD),
        # POST / -> receives JSON-RPC calls such as "SendMessage".
        *create_jsonrpc_routes(handler, rpc_url="/"),
    ]
    uvicorn.run(Starlette(routes=routes), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
