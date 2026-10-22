"""CV Matcher agent: checks a CV (PDF) against the Job Analyst's requirements.

The first agent that pauses and asks the user (A2A input-required).
Instructions: prompts/cv_matcher.md. Checklist and questions: schema.py. Score: scoring.py.

Run with:  python -m agents.cv_matcher
"""

import json

import uvicorn
from google.protobuf.json_format import MessageToDict
from starlette.applications import Starlette

from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    TaskState,
    UnsupportedOperationError,
)

from agents.cv_matcher.schema import (
    CHECK_SCHEMA,
    apply_model_checks,
    build_checklist,
    build_questions,
    checklist_as_text,
    merge_answers,
)
from agents.cv_matcher.scoring import build_report
from agents.cv_text import extract_pdf_text
from agents.model_client import PROJECT_ROOT, ModelError, ask_model, read_setting

HOST = "localhost"
PORT = 9002
URL = f"http://{HOST}:{PORT}"

PROMPT_FILE = PROJECT_ROOT / "prompts" / "cv_matcher.md"
MODEL_TIMEOUT_SECONDS = 300  # one call checks every requirement, which can take a while
STATE_KEY = "cv_matcher_state"


# AGENT CARD: the public "business card" other agents read to learn
# who this agent is, where to reach it, and what skills it has.
AGENT_CARD = AgentCard(
    name="CV Matcher",
    description="Compares a CV with a job's requirements and asks yes/no questions when unsure.",
    version="0.2.0",
    supported_interfaces=[
        AgentInterface(url=URL, protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    capabilities=AgentCapabilities(streaming=False),
    # Input: the Job Analyst's requirements (JSON data part) and the CV (PDF file part).
    default_input_modes=["application/json", "application/pdf"],
    default_output_modes=["application/json"],
    skills=[
        AgentSkill(
            id="match_cv_to_job",
            name="Match CV to job requirements",
            description=(
                "Checks every job requirement against a CV (PDF), with an exact CV quote as "
                "proof. Asks up to 5 yes/no questions for unclear required items, then returns "
                "a match score (required counts 2, preferred 1) and a short report."
            ),
            tags=["cv", "matching", "job requirements"],
            examples=["Requirements JSON from the Job Analyst + cv.pdf"],
        )
    ],
)


class CvMatcherExecutor(AgentExecutor):
    """The agent's logic. execute() runs for the first message AND for each answer message."""

    def __init__(self, model: str) -> None:
        self.model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task

        # TASK: create it on the first message. A follow-up message with the same
        # task id finds the stored task here instead (context.current_task).
        if task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))

        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        if task is not None and task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            await self._continue_with_answers(context, task, updater)
        else:
            await self._start_analysis(context, updater)

    async def _start_analysis(self, context: RequestContext, updater: TaskUpdater) -> None:
        parts = context.message.parts

        # FILE PART: the CV arrives as raw bytes (base64 on the wire) with a media type.
        pdf_parts = [p for p in parts if p.HasField("raw")]
        # DATA PART: the Job Analyst's requirements JSON.
        data_parts = [d for d in get_data_parts(parts) if isinstance(d, dict)]
        if not pdf_parts or not data_parts:
            await self._fail(updater, "Expected one data part (requirements JSON) and one file part (CV as PDF).")
            return
        requirements = data_parts[0]

        await updater.start_work()  # STATUS: working

        try:
            cv_text = extract_pdf_text(pdf_parts[0].raw)
        except ValueError as error:
            await self._fail(updater, str(error))
            return

        checklist = build_checklist(requirements)
        if not checklist:
            await self._fail(updater, "The requirements contain no items to check.")
            return

        try:
            analysis = await self._check_with_model(checklist, cv_text)
        except (ModelError, ValueError) as error:
            await self._fail(updater, str(error))
            return

        questions = build_questions(analysis)
        if questions:
            await self._ask_user(updater, requirements, analysis, questions)
            return
        await self._finish(updater, requirements, analysis)

    async def _check_with_model(self, checklist: list[dict], cv_text: str) -> list[dict]:
        """One model call for all requirements, then the quote check in plain Python."""
        instructions = PROMPT_FILE.read_text(encoding="utf-8")
        user_message = f"Requirements:\n{checklist_as_text(checklist)}\n\nCV:\n{cv_text}"

        # MODEL CALL (through the shared model client), schema-enforced, temperature 0.
        answer = await ask_model(
            user_message,
            self.model,
            system=instructions,
            json_schema=CHECK_SCHEMA,
            timeout=MODEL_TIMEOUT_SECONDS,
        )
        try:
            checks = json.loads(answer)["checks"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise ValueError(f"The model's answer is not the expected JSON: {answer[:200]!r}") from e

        # QUOTE CHECK: a "found" only stays found if its quote really appears in the CV.
        return apply_model_checks(checklist, checks, cv_text)

    async def _ask_user(self, updater, requirements, analysis, questions) -> None:
        text = "Please answer yes or no:\n" + "\n".join(f"{q['id']}: {q['question']}" for q in questions)
        message = updater.new_agent_message(
            [
                new_text_part(text),
                # The same questions as data, so a program can answer by id.
                new_data_part({"questions": [{"id": q["id"], "question": q["question"]} for q in questions]}),
            ]
        )
        # STATE SAVED: the half-finished analysis goes into the task's metadata.
        # The SDK merges status-update metadata into task.metadata in the task store.
        state = {STATE_KEY: {"requirements": requirements, "analysis": analysis, "questions": questions}}

        # INPUT-REQUIRED: pause the task. execute() returns; the questions are the status message.
        await updater.update_status(
            TaskState.TASK_STATE_INPUT_REQUIRED, message=message, metadata=state
        )

    async def _continue_with_answers(self, context: RequestContext, task, updater: TaskUpdater) -> None:
        # STATE SAVED (read back): the analysis we stored when we paused.
        state = MessageToDict(task.metadata)[STATE_KEY]
        requirements, analysis, questions = state["requirements"], state["analysis"], state["questions"]

        answers = next(
            (d["answers"] for d in get_data_parts(context.message.parts)
             if isinstance(d, dict) and isinstance(d.get("answers"), dict)),
            None,
        )
        if answers is None:
            # Not an answer we understand: ask the same questions again.
            await self._ask_user(updater, requirements, analysis, questions)
            return

        await updater.start_work()  # STATUS: working again
        # ANSWERS MERGED: yes -> confirmed, no -> missing.
        analysis = merge_answers(analysis, questions, answers)
        await self._finish(updater, requirements, analysis)

    async def _finish(self, updater: TaskUpdater, requirements: dict, analysis: list[dict]) -> None:
        # SCORE CALCULATED (inside build_report, plain Python).
        report = build_report(requirements, analysis)
        # Which code produced this result (same as the agent card version).
        report["agent_version"] = AGENT_CARD.version
        # ARTIFACT: one DATA part with the report.
        await updater.add_artifact(
            [new_data_part(report, media_type="application/json")], name="cv_match_report"
        )
        await updater.complete()  # STATUS: completed

    async def _fail(self, updater: TaskUpdater, error: str) -> None:
        # FAILED STATUS: final state, with the error as a text message.
        await updater.failed(updater.new_agent_message([new_text_part(f"CV Matcher failed: {error}")]))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()


def main() -> None:
    model = read_setting("CV_MATCHER_MODEL")
    print(f"CV Matcher using model: {model}")

    handler = DefaultRequestHandler(
        agent_executor=CvMatcherExecutor(model),
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
