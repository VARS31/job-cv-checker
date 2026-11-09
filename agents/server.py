"""Serving an agent: the same few lines for all four agents.

- the A2A routes: GET /.well-known/agent-card.json serves the AGENT CARD, POST / receives JSON-RPC calls
  such as "SendMessage"; the request handler keeps tasks in memory;
- tracing: set up for this process (if TRACING=on), and the middleware that joins the agent's spans to the
  orchestrator's trace;
- where to listen: localhost by default. In Docker it is 0.0.0.0 (AGENT_BIND_HOST), because a container's
  localhost can't be reached from outside; docker-compose.yml publishes the port on 127.0.0.1 only, so the
  agent card can keep saying http://localhost:<port>.
"""

import uvicorn
from starlette.applications import Starlette

from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard

from agents import tracing
from agents.model_client import read_setting


def serve(card: AgentCard, executor: AgentExecutor, port: int, service: str) -> None:
    """Run one agent's HTTP server until it is stopped. service: its name in the trace viewers."""
    tracing.setup(service, check_viewers=False)
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore(), agent_card=card)
    routes = [
        # GET /.well-known/agent-card.json -> serves the AGENT CARD.
        *create_agent_card_routes(card),
        # POST / -> receives JSON-RPC calls such as "SendMessage".
        *create_jsonrpc_routes(handler, rpc_url="/"),
    ]
    app = tracing.TraceContextMiddleware(Starlette(routes=routes))
    uvicorn.run(app, host=read_setting("AGENT_BIND_HOST", "localhost"), port=port)
