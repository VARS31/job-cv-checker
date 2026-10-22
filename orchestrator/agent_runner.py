"""Talking to the agents: read their cards, run one step, handle input-required."""

import time
import uuid
from dataclasses import dataclass, field

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text, new_data_part, new_text_part
from a2a.types import AgentCard, Message, Role, SendMessageRequest, TaskState
from a2a.utils.errors import A2AError  # base of all client errors and server error replies

from agents.model_client import read_setting
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


def _ask_yes_no(questions: list[dict]) -> list:
    answers = {}
    for q in questions:
        while True:
            reply = input(f"   {q['question']} [y/n] ").strip().lower()
            if reply in ("y", "yes", "n", "no"):
                answers[q["id"]] = reply.startswith("y")
                break
    return [new_data_part({"answers": answers})]


def _ask_free_text(question: str) -> list:
    print(f"   {question}")
    while not (reply := input("   > ").strip()):
        pass
    return [new_text_part(reply)]


async def _send(agent: ConnectedAgent, message: Message):
    start = time.perf_counter()
    async for response in agent.client.send_message(SendMessageRequest(message=message)):
        task = response.task
    return task, time.perf_counter() - start


async def run_step(agent: ConnectedAgent, parts: list, context_id: str) -> StepResult:
    """Send one message, answer questions until the task finishes, return the result."""
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
                answer_parts = _ask_yes_no(questions)
            else:
                print(" input-required (free text)")
                answer_parts = _ask_free_text(get_message_text(task.status.message))

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
    except (A2AError, httpx.HTTPError) as error:
        # FAILURE HANDLED: the agent crashed or the connection broke.
        result.state, result.error = "error", f"{type(error).__name__}: {error}"
        print(" error")
        return result

    result.state = _state_word(task.status.state)
    result.artifacts = list(task.artifacts)
    if task.status.state != TaskState.TASK_STATE_COMPLETED and task.status.HasField("message"):
        result.error = get_message_text(task.status.message)
    print(f" {result.state} ({result.seconds:.0f} s)")
    return result
