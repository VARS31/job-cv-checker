"""Job Analyst agent (plumbing test: no model calls yet).

Run with:  python -m agents.job_analyst
"""

import uvicorn
from starlette.applications import Starlette

from a2a.helpers import new_task_from_user_message, new_text_part
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

HOST = "localhost"
PORT = 9001
URL = f"http://{HOST}:{PORT}"


# AGENT CARD: the public "business card" other agents read to learn
# who this agent is, where to reach it, and what skills it has.
AGENT_CARD = AgentCard(
    name="Job Analyst",
    description="Reads a job ad and pulls out the key requirements.",
    version="0.1.0",
    # Where and how to talk to this agent: JSON-RPC over HTTP, A2A protocol 1.0.
    supported_interfaces=[
        AgentInterface(url=URL, protocol_binding="JSONRPC", protocol_version="1.0")
    ],
    capabilities=AgentCapabilities(streaming=False),
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    skills=[
        AgentSkill(
            id="analyze_job_ad",
            name="Analyze job ad",
            description="Reads a job ad and lists its key requirements.",
            tags=["job ad", "requirements"],
            examples=["Here is a job ad: ..."],
        )
    ],
)


class JobAnalystExecutor(AgentExecutor):
    """The agent's own logic. The SDK calls execute() for every incoming message."""

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

        # ARTIFACT: the result of the task, made of parts (here one text part).
        reply = f"Job Analyst received your job ad ({len(job_ad)} characters)."
        await updater.add_artifact([new_text_part(reply)], name="job_analysis")

        # STATUS: final state; the task is done.
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise UnsupportedOperationError()


def main() -> None:
    # The request handler connects the HTTP layer to our executor and keeps tasks in memory.
    handler = DefaultRequestHandler(
        agent_executor=JobAnalystExecutor(),
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
