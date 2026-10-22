"""Job Analyst agent: reads a job ad and returns its key requirements as JSON.

Instructions: prompts/job_analyst.md. Output shape: schema.py.

Run with:  python -m agents.job_analyst
"""

import json

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_data_part, new_task_from_user_message, new_text_part
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
    UnsupportedOperationError,
)

from agents.job_analyst.schema import REQUIREMENTS_SCHEMA, clean_requirements
from agents.model_client import PROJECT_ROOT, ModelError, ask_model, read_setting

HOST = "localhost"
PORT = 9001
URL = f"http://{HOST}:{PORT}"

# The agent's instructions live in a Markdown file so they can be edited without touching code.
PROMPT_FILE = PROJECT_ROOT / "prompts" / "job_analyst.md"


# AGENT CARD: the public "business card" other agents read to learn
# who this agent is, where to reach it, and what skills it has.
AGENT_CARD = AgentCard(
    name="Job Analyst",
    description="Reads a job ad and pulls out the key requirements.",
    version="0.4.0",
    # Where and how to talk to this agent: JSON-RPC over HTTP, A2A protocol 1.0.
    supported_interfaces=[
        AgentInterface(url=URL, protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["application/json"],
    skills=[
        AgentSkill(
            id="analyze_job_ad",
            name="Analyze job ad",
            description=(
                "Reads a job ad and returns its requirements as JSON: title, company, "
                "location, education, experience, hard and soft skills (required vs. "
                "preferred), languages, and responsibilities."
            ),
            tags=["job ad", "requirements"],
            examples=["Here is a job ad: ..."],
        )
    ],
)


async def extract_requirements(job_ad: str, model: str) -> dict:
    """Ask the model for the requirements and check the answer. Raises on failure."""
    # Read the prompt on every request, so edits to the file apply without a restart.
    instructions = PROMPT_FILE.read_text(encoding="utf-8")

    # MODEL CALL (through the shared model client): instructions as the system message,
    # the job ad as the user message, and the schema to enforce JSON.
    answer = await ask_model(
        job_ad, model, system=instructions, json_schema=REQUIREMENTS_SCHEMA
    )

    # JSON OUTPUT CHECKED: the answer must parse and have exactly our fields.
    try:
        requirements = json.loads(answer)
    except json.JSONDecodeError as e:
        raise ValueError(f"The model's answer is not valid JSON: {answer[:200]!r}") from e
    if not isinstance(requirements, dict) or set(requirements) != set(REQUIREMENTS_SCHEMA["required"]):
        raise ValueError(f"The model's JSON does not have the expected fields: {answer[:200]!r}")

    # CLEAN-UP in plain Python: trim spaces, remove duplicates within and across fields.
    return clean_requirements(requirements)


class JobAnalystExecutor(AgentExecutor):
    """The agent's own logic. The SDK calls execute() for every incoming message."""

    def __init__(self, model: str) -> None:
        self.model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # MESSAGE: the incoming message from the client; we take the text of its parts.
        job_ad = context.get_user_input()

        # TASK: one unit of work with an id. Create it on the first message.
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))

        # TaskUpdater sends task events (status changes, artifacts) for us.
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        # STATUS: tell the client we are working on it.
        await updater.start_work()

        try:
            requirements = await extract_requirements(job_ad, self.model)
        except (ModelError, ValueError) as error:
            # FAILED STATUS: final state, with the error as a text message in the status.
            await updater.failed(
                updater.new_agent_message([new_text_part(f"Job Analyst failed: {error}")])
            )
            return

        # ARTIFACT: the result of the task. Its one part is a DATA part (structured JSON),
        # not text. Note: protobuf stores all numbers as floats, so 3 arrives as 3.0.
        await updater.add_artifact(
            [new_data_part(requirements, media_type="application/json")],
            name="job_requirements",
        )

        # STATUS: final state; the task is done.
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()


def main() -> None:
    model = read_setting("JOB_ANALYST_MODEL")
    print(f"Job Analyst using model: {model}")

    # The request handler connects the HTTP layer to our executor and keeps tasks in memory.
    handler = DefaultRequestHandler(
        agent_executor=JobAnalystExecutor(model),
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
