"""Cover Letter Writer agent: writes a cover letter from the job requirements,
the CV Matcher's report and the CV, after asking the user one free-text question.

Instructions: prompts/cover_letter_writer.md. Schema, claims and style checks: schema.py.

Run with:  python -m agents.cover_letter_writer
"""

import json
import time

from google.protobuf.json_format import MessageToDict

from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
    UnsupportedOperationError,
)

from agents import tracing
from agents.cover_letter_writer.schema import (
    LETTER_SCHEMA,
    body_paragraphs,
    build_model_input,
    build_question,
    build_rewrite_input,
    check_claims,
    fix_dashes,
    style_warnings,
)
from agents.cv_text import extract_pdf_text, today_iso
from agents.model_client import (
    PROJECT_ROOT,
    USAGE_KEY,
    ModelError,
    Usage,
    ask_model,
    read_setting,
    startup_check,
)
from agents.server import serve

HOST = "localhost"  # the address in the agent card; where the server listens: agents/server.py
PORT = 9003
URL = f"http://{HOST}:{PORT}"

PROMPT_FILE = PROJECT_ROOT / "prompts" / "cover_letter_writer.md"
WRITING_TEMPERATURE = 0.4  # a little variation helps writing; facts are checked afterwards (Ollama only)
MODEL_TIMEOUT_SECONDS = 300
STATE_KEY = "cover_letter_state"


# AGENT CARD: the public "business card" other agents read to learn
# who this agent is, where to reach it, and what skills it has.
AGENT_CARD = AgentCard(
    name="Cover Letter Writer",
    description="Writes an honest cover letter from the job requirements, the CV match report and the CV.",
    version="0.3.0",
    supported_interfaces=[
        AgentInterface(url=URL, protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    capabilities=AgentCapabilities(streaming=False),
    # Input: requirements + match report (JSON data parts) and the CV (PDF file part).
    default_input_modes=["application/json", "application/pdf"],
    # Output: the letter as text, plus the checked claims as JSON.
    default_output_modes=["text/plain", "application/json"],
    skills=[
        AgentSkill(
            id="write_cover_letter",
            name="Write cover letter",
            description=(
                "Asks why the user wants the role, then writes a 3-paragraph cover letter using "
                "only matched and confirmed items. Every factual claim is checked against the CV "
                "or the user's answer; unproven claims are removed or listed for review."
            ),
            tags=["cover letter", "writing", "job application"],
            examples=["Requirements JSON + CV Matcher report JSON + cv.pdf"],
        )
    ],
)


def split_inputs(parts) -> tuple[dict | None, dict | None]:
    """Find the two data parts: the requirements and the CV Matcher's report."""
    requirements = report = None
    for data in get_data_parts(parts):
        if isinstance(data, dict) and "score_percent" in data:
            report = data
        elif isinstance(data, dict) and "hard_skills_required" in data:
            requirements = data
    return requirements, report


class CoverLetterExecutor(AgentExecutor):
    """The agent's logic. execute() runs for the first message AND for the answer message."""

    def __init__(self, model: str) -> None:
        self.model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        # TASK: create it on the first message; a follow-up with the same task id finds it here.
        if task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # SPAN: this message in the trace (a no-op when tracing is off).
        if task is not None and task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            with tracing.agent_task("Cover Letter Writer", AGENT_CARD.version, context, "answer received"):
                await self._continue_with_answer(context, task, updater)
        else:
            with tracing.agent_task("Cover Letter Writer", AGENT_CARD.version, context, "new task"):
                await self._start(context, updater)

    async def _start(self, context: RequestContext, updater: TaskUpdater) -> None:
        parts = context.message.parts
        # FILE PART: the CV as raw bytes. DATA PARTS: requirements and match report.
        pdf_parts = [p for p in parts if p.HasField("raw")]
        requirements, report = split_inputs(parts)
        if not pdf_parts or requirements is None or report is None:
            await self._fail(
                updater,
                "Expected two data parts (requirements JSON, CV Matcher report JSON) and one file part (CV as PDF).",
            )
            return

        await updater.start_work()  # STATUS: working
        try:
            cv_text = extract_pdf_text(pdf_parts[0].raw)
        except ValueError as error:
            await self._fail(updater, str(error))
            return

        state = {"requirements": requirements, "report": report, "cv_text": cv_text}
        await self._ask_user(updater, state)

    async def _ask_user(self, updater: TaskUpdater, state: dict) -> None:
        question = build_question(state["requirements"])
        # paused_at: when the task paused, so the trace can show how long the agent waited for the answer.
        state = {**state, "paused_at": time.time()}
        # STATE SAVED: inputs and CV text go into task.metadata, so the PDF isn't read again.
        # INPUT-REQUIRED: pause the task; the question is the status message (free text).
        await updater.update_status(
            TaskState.TASK_STATE_INPUT_REQUIRED,
            message=updater.new_agent_message([new_text_part(question)]),
            metadata={STATE_KEY: state},
        )

    async def _continue_with_answer(self, context: RequestContext, task, updater: TaskUpdater) -> None:
        # STATE SAVED (read back): what we stored when we paused.
        state = MessageToDict(task.metadata)[STATE_KEY]

        # HUMAN IN THE LOOP: how long the task was paused, waiting for this answer.
        if "paused_at" in state:
            waited = round(time.time() - float(state["paused_at"]), 3)
            tracing.set_attributes(tracing.current_span(), {"cvchecker.hitl.waited_seconds": waited})

        # ANSWER MERGED: the free-text answer is the text part(s) of the new message.
        answer = context.get_user_input().strip()
        if not answer:
            await self._ask_user(updater, state)  # empty answer: ask the same question again
            return

        await updater.start_work()  # STATUS: working again
        # USAGE: tokens, cost and time of this task's model calls (one, or two with the rewrite).
        usage = Usage(self.model)
        try:
            result = await self._write_letter(state, answer, usage, context.context_id)
        except (ModelError, ValueError) as error:
            await self._fail(updater, str(error), usage)
            return

        # ARTIFACT: the letter as a TEXT part, the checked claims as a DATA part.
        await updater.add_artifact(
            [
                new_text_part(result["letter"], media_type="text/plain"),
                new_data_part(result["details"], media_type="application/json"),
            ],
            name="cover_letter",
            # The artifact's METADATA says which model produced it and what it cost.
            metadata={USAGE_KEY: usage.as_metadata()},
        )
        await updater.complete()  # STATUS: completed

    async def _ask_model(self, user_message: str, usage: Usage, run_id: str) -> tuple[str, list[dict]]:
        instructions = PROMPT_FILE.read_text(encoding="utf-8")
        # MODEL CALL (through the shared model client), schema-enforced, temperature 0.4 on Ollama.
        answer = await ask_model(
            user_message,
            self.model,
            system=instructions,
            json_schema=LETTER_SCHEMA,
            temperature=WRITING_TEMPERATURE,
            timeout=MODEL_TIMEOUT_SECONDS,
            usage=usage,
            run_id=run_id,
        )
        try:
            data = json.loads(answer)
            # DASHES FIXED in plain Python: em-/en-dashes used as pauses become commas or full stops.
            return fix_dashes(data["letter"].strip()), data["claims"]
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
            raise ValueError(f"The model's answer is not the expected JSON: {answer[:200]!r}") from e

    async def _write_letter(self, state: dict, answer: str, usage: Usage, run_id: str) -> dict:
        requirements, report, cv_text = state["requirements"], state["report"], state["cv_text"]
        # TODAY'S DATE goes into the input, so "09/2019 - today" in the CV is counted correctly.
        model_input = build_model_input(requirements, report, answer, cv_text, today_iso())

        letter, claims = await self._ask_model(model_input, usage, run_id)
        # CLAIMS CHECKED: every quote must appear in the CV, or in the answer / confirmed items.
        proven, unproven = self._checked_claims(1, claims, cv_text, answer, report)

        rewrite_used = False
        if unproven:
            # REWRITE: ask once more, without the unproven claims, then check again.
            rewrite_used = True
            first_unproven = unproven
            letter, claims = await self._ask_model(build_rewrite_input(model_input, letter, unproven), usage, run_id)
            proven, unproven = self._checked_claims(2, claims, cv_text, answer, report)
        else:
            first_unproven = []

        details = {
            "agent_version": AGENT_CARD.version,
            "claims": proven,
            # Still unproven after the rewrite: kept in the letter, listed for your review.
            "unproven_claims": unproven,
            "rewrite_used": rewrite_used,
            "removed_in_rewrite": first_unproven,
            "style_warnings": style_warnings(letter, claims),
            "word_count": len(letter.split()),
            "body_paragraphs": len(body_paragraphs(letter)),
        }
        return {"letter": letter, "details": details}

    @staticmethod
    def _checked_claims(attempt: int, claims, cv_text: str, answer: str, report: dict):
        """The claims check (a grounding check), with its own span: counts always, the claims only as content."""
        with tracing.span("grounding: claims check", {
            "openinference.span.kind": "EVALUATOR", "cvchecker.claims.attempt": attempt,
        }) as span:
            proven, unproven = check_claims(claims, cv_text, answer, report)
            tracing.set_attributes(span, {
                "cvchecker.claims.total": len(claims),
                "cvchecker.claims.proven": len(proven),
                "cvchecker.claims.unproven": len(unproven),
            })
            tracing.set_content(span, {"cvchecker.claims.unproven_text": [c["claim"] for c in unproven]})
        return proven, unproven

    async def _fail(self, updater: TaskUpdater, error: str, usage: Usage | None = None) -> None:
        # FAILED STATUS: final state, with the error as a text message (and the usage so far, if any).
        metadata = {USAGE_KEY: usage.as_metadata()} if usage else None
        await updater.failed(
            updater.new_agent_message([new_text_part(f"Cover Letter Writer failed: {error}")], metadata=metadata)
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()


def main() -> None:
    # The model belongs to the agent: read once at startup, checked before the server starts.
    model = read_setting("COVER_LETTER_MODEL")
    startup_check("Cover Letter Writer", model)
    # SERVER: the A2A routes, tracing and where to listen are the same for all agents (agents/server.py).
    serve(AGENT_CARD, CoverLetterExecutor(model), PORT, "cover-letter-writer")


if __name__ == "__main__":
    main()
