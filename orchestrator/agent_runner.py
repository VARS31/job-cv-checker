"""Talking to the agents: read their cards, run one step, handle input-required, read what each step used."""

import time
import uuid
from dataclasses import dataclass, field

import httpx
from google.protobuf.json_format import MessageToDict

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text, new_data_part, new_text_part
from a2a.types import AgentCard, Message, Role, SendMessageRequest, TaskState
from a2a.utils.errors import A2AError  # base of all client errors and server error replies

from agents.model_client import USAGE_KEY, read_setting
from orchestrator.pipeline import Step

MAX_INPUT_ROUNDS = 3  # questions per agent before the orchestrator gives up


@dataclass
class ConnectedAgent:
    step: Step
    url: str
    card: AgentCard
    client: object


@dataclass
class StepResult:
    agent: str
    url: str
    agent_version: str
    task_id: str | None = None
    context_id: str | None = None
    state: str = "not started"
    seconds: float = 0.0  # time spent waiting for the agent (not for you)
    input_rounds: int = 0
    error: str | None = None
    # What the agent reports in its result metadata: the model is the agent's own choice.
    model: str | None = None
    provider: str | None = None  # "ollama" (local) or "anthropic" (cloud)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_seconds: float = 0.0
    model_notes: list = field(default_factory=list)
    answers: list = field(default_factory=list)  # every question the agent asked, with the answer given
    artifacts: list = field(default_factory=list)

    def for_log(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "artifacts"}


def _state_word(state: int) -> str:
    """TASK_STATE_INPUT_REQUIRED -> input-required"""
    return TaskState.Name(state).removeprefix("TASK_STATE_").lower().replace("_", "-")


async def read_agent_cards(steps: list[Step], http: httpx.AsyncClient) -> list[ConnectedAgent] | None:
    """AGENT CARDS READ: check every agent before any work. None if one is unreachable."""
    agents, problems = [], []
    factory = ClientFactory(ClientConfig(httpx_client=http, streaming=False))
    for step in steps:
        url = read_setting(step.url_setting, step.default_url)
        try:
            card = await A2ACardResolver(http, url).get_agent_card()
        except (A2AError, httpx.HTTPError) as error:
            problems.append((step, url, error))
            continue
        agents.append(ConnectedAgent(step, url, card, factory.create(card)))
        print(f"✓ {card.name} {card.version} at {url}")
    for step, url, _ in problems:
        print(f"✗ {step.name} is not reachable at {url}")
        print(f"  Start it with:  {step.start_command}")
    if problems:
        print("Or start all agents at once with:  python scripts/start_agents.py")
    return None if problems else agents


def _usage_from(task) -> dict | None:
    """The agent's usage report: in the artifact's metadata, or in the status message when it failed."""
    sources = [artifact.metadata for artifact in task.artifacts]
    if task.status.HasField("message"):
        sources.append(task.status.message.metadata)
    for metadata in sources:
        data = MessageToDict(metadata)
        if USAGE_KEY in data:
            return data[USAGE_KEY]
    return None


def _add_usage(result: StepResult, usage: dict | None) -> None:
    if not usage:
        return
    # Protobuf turns every number into a float, so counts are turned back into ints here.
    result.model, result.provider = usage.get("model"), usage.get("provider")
    result.model_calls = int(usage.get("calls", 0))
    result.input_tokens, result.output_tokens = int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
    result.cost_usd = float(usage.get("cost_usd", 0.0))
    result.model_seconds = float(usage.get("model_seconds", 0.0))
    result.model_notes = list(usage.get("notes", []))


def _usage_text(result: StepResult) -> str:
    """', ministral-3:8b, local' or ', claude-haiku-5-5, $0.0012' for the progress line."""
    if not result.model:
        return ""
    return f", {result.model}, " + (f"${result.cost_usd:.4f}" if result.provider == "anthropic" else "local")


async def _send(agent: ConnectedAgent, message: Message):
    start = time.perf_counter()
    async for response in agent.client.send_message(SendMessageRequest(message=message)):
        task = response.task
    return task, time.perf_counter() - start


async def run_step(agent: ConnectedAgent, parts: list, context_id: str, answers) -> StepResult:
    """Send one message, answer questions until the task finishes, return the result.

    answers: where the answers come from (orchestrator/answers.py: the terminal, or a file).
    """
    step = agent.step
    result = StepResult(agent=step.name, url=agent.url, agent_version=agent.card.version)
    # One context id for the whole run: every agent's task belongs to the same conversation.
    message = Message(role=Role.ROLE_USER, message_id=str(uuid.uuid4()), context_id=context_id, parts=parts)

    print(f"→ {step.name}: working…", end="", flush=True)
    try:
        task, seconds = await _send(agent, message)
        result.seconds += seconds
        result.task_id, result.context_id = task.id, task.context_id

        # INPUT-REQUIRED HANDLED: one generic loop for every agent.
        while task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            if result.input_rounds == MAX_INPUT_ROUNDS:
                result.state = "input-required"
                result.error = f"{step.name} still needs input after {MAX_INPUT_ROUNDS} rounds; stopping."
                print(f" input-required (gave up after {MAX_INPUT_ROUNDS} rounds)")
                return result
            result.input_rounds += 1

            # Questions with ids (a data part) -> y/n each. Otherwise -> free text.
            questions = next(
                (d["questions"] for d in get_data_parts(task.status.message.parts)
                 if isinstance(d, dict) and isinstance(d.get("questions"), list)),
                None,
            )
            if questions:
                print(f" input-required ({len(questions)} question{'s' if len(questions) != 1 else ''})")
                yes_no = {}
                for q in questions:
                    yes_no[q["id"]] = answers.yes_no(q["question"])
                    result.answers.append({
                        "question": q["question"], "answer": "yes" if yes_no[q["id"]] else "no", "from": answers.source,
                    })
                answer_parts = [new_data_part({"answers": yes_no})]
            else:
                print(" input-required (free text)")
                question = get_message_text(task.status.message)
                reply_text = answers.free_text(question)
                result.answers.append({"question": question, "answer": reply_text, "from": answers.source})
                answer_parts = [new_text_part(reply_text)]

            # Same task id and context id -> the agent continues the paused task.
            reply = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                task_id=task.id,
                context_id=task.context_id,
                parts=answer_parts,
            )
            print(f"→ {step.name}: working…", end="", flush=True)
            task, seconds = await _send(agent, reply)
            result.seconds += seconds
    except (A2AError, httpx.HTTPError, ValueError) as error:
        # FAILURE HANDLED: the agent crashed, the connection broke, or the answers file has no answer.
        result.state, result.error = "error", f"{type(error).__name__}: {error}"
        print(" error")
        return result

    result.state = _state_word(task.status.state)
    result.artifacts = list(task.artifacts)
    _add_usage(result, _usage_from(task))
    if task.status.state != TaskState.TASK_STATE_COMPLETED and task.status.HasField("message"):
        result.error = get_message_text(task.status.message)
    print(f" {result.state} ({result.seconds:.0f} s{_usage_text(result)})")
    return result
