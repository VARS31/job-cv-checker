"""The one place where the project talks to a model.

All model calls in the project go through ask_model(). The model belongs to the agent: each agent reads
its model name from its settings at startup (startup_check) and passes it in here with every call.

Local by default, cloud optional. The model name decides where a call goes:
- a name starting with "claude-" (e.g. claude-haiku-5-5) goes to Anthropic's API. That costs money,
  and the text of the request (job ad, CV, letter) leaves this machine;
- any other name (e.g. ministral-3:8b) goes to Ollama on this machine (OLLAMA_URL in .env).

What is different on Claude, on purpose:
- No temperature. The API version the SDK uses (2026-10-21) rejects temperature on every model, so
  Claude runs at its defaults: adaptive thinking at the model's default effort. Runs are not exactly
  repeatable.
- The same JSON schemas, adapted: the API enforces the JSON shape but not array lengths. Those limits
  move into the field descriptions (the SDK's transform_schema) and are checked here in plain Python.
- Every call is checked against the budget before it is made, and counted after it (agents/budget.py).
- The API key is read here and handed to the SDK. It is never printed, logged or stored.
"""

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from agents.budget import Budget, BudgetExceeded, call_cost, has_price, worst_case_cost

DEFAULT_CONTEXT_SIZE = 8192  # tokens (Ollama only)
DEFAULT_TEMPERATURE = 0.0  # 0 = always pick the most likely word (Ollama only; Claude takes no temperature)
TIMEOUT_SECONDS = 120  # small local models can be slow, especially on first load
CONTEXT_WARNING_SHARE = 0.8  # warn when a request fills more than 80% of the context

CLAUDE_PREFIX = "claude-"
CLAUDE_MAX_TOKENS = 16000  # thinking counts towards it; a call that reaches it fails instead of giving half an answer
KEY_NAME = "ANTHROPIC_API_KEY"
DEFAULT_RUN_LIMIT_USD = "0.50"
DEFAULT_TOTAL_LIMIT_USD = "3.00"

# Agents put their Usage under this key in their result metadata; the orchestrator reads it from there.
USAGE_KEY = "model_usage"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RESULTS_DIR = PROJECT_ROOT / "results"
BUDGET_FILE = RESULTS_DIR / "cloud_spend.json"  # gitignored, like all of results/

_agent_name = "unknown agent"  # set by startup_check(); written next to each paid call in the budget file
_claude_client = None  # one SDK client per agent process, created on the first Claude call


class ModelError(Exception):
    """Raised when the model can't be reached, returns an error, or the budget guard stops a call."""


def read_setting(name: str, default: str | None = None) -> str:
    """Return a setting from the environment, falling back to the .env file, then the default."""
    if name in os.environ:
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip()
    if default is not None:
        return default
    raise RuntimeError(f"Setting {name} is missing. Add it to .env (see .env.example).")


def model_folder_name(model: str) -> str:
    """Turn a model name like 'llama3.2:3b' into a safe folder name: 'llama3.2_3b'."""
    return model.replace(":", "_").replace("/", "_")


def is_claude_model(model: str) -> bool:
    """A Claude model name means Claude (cloud); anything else means Ollama (local)."""
    return model.strip().lower().startswith(CLAUDE_PREFIX)


@dataclass
class Usage:
    """What one task spent on model calls. The agent sends it back in its result metadata (USAGE_KEY)."""

    model: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0  # on Claude this includes the thinking tokens: that's what is billed
    cost_usd: float = 0.0
    model_seconds: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def provider(self) -> str:
        return "anthropic" if is_claude_model(self.model) else "ollama"

    def add(self, input_tokens: int, output_tokens: int, cost_usd: float, seconds: float) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost_usd
        self.model_seconds += seconds

    def as_metadata(self) -> dict:
        return {
            "model": self.model,
            "provider": self.provider,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "model_seconds": round(self.model_seconds, 1),
            "notes": self.notes,
        }

    @classmethod
    def from_metadata(cls, data: dict) -> "Usage":
        """Read it back (e.g. from a paused task's state). Protobuf turns every number into a float."""
        return cls(
            model=data["model"],
            calls=int(data.get("calls", 0)),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cost_usd=float(data.get("cost_usd", 0.0)),
            model_seconds=float(data.get("model_seconds", 0.0)),
            notes=list(data.get("notes", [])),
        )


def budget() -> Budget:
    """The budget guard, with the limits from .env (defaults: $0.50 per run, $3.00 in total)."""
    return Budget(
        BUDGET_FILE,
        run_limit=float(read_setting("BUDGET_PER_RUN_USD", DEFAULT_RUN_LIMIT_USD)),
        total_limit=float(read_setting("BUDGET_TOTAL_USD", DEFAULT_TOTAL_LIMIT_USD)),
    )


# ---------------------------------------------------------------------------------------------------
# Startup check: run once when an agent starts. It never falls back to another model.
# ---------------------------------------------------------------------------------------------------

def startup_check(agent_name: str, model: str) -> None:
    """Stop the agent (SystemExit, with a clear message) if its model can't be used. Otherwise say where calls go."""
    global _agent_name
    _agent_name = agent_name

    if not is_claude_model(model):
        if not read_setting("OLLAMA_URL", ""):
            raise SystemExit(f"{agent_name}: OLLAMA_URL is not set. Add it to .env (see .env.example). Not starting.")
        print(f"{agent_name} using model: {model} (local, Ollama)")
        return

    if not has_price(model):
        raise SystemExit(
            f"{agent_name}: there is no price for {model} in agents/budget.py, so the budget guard "
            "couldn't count its cost. Add the price there or choose another model. Not starting."
        )
    key = read_setting(KEY_NAME, "")
    if not key:
        raise SystemExit(
            f"{agent_name}: {model} is a Claude model, but {KEY_NAME} is not set. Add it to .env, "
            "or start the agents with --preset local. Not starting."
        )
    _check_key_with_api(agent_name, model, key)

    guard = budget()
    _, spent = guard.spent()
    print(f"{agent_name} using model: {model} (Claude, cloud). The text it receives is sent to Anthropic.")
    print(f"{agent_name}: cloud spend so far ${spent:.4f} of ${guard.total_limit:.2f} (limit per run ${guard.run_limit:.2f})")


def _check_key_with_api(agent_name: str, model: str, key: str) -> None:
    """Ask the API about the model. That uses no tokens, so the check is free."""
    import anthropic  # only agents with a Claude model need the SDK

    try:
        anthropic.Anthropic(api_key=key, max_retries=1, timeout=20).models.retrieve(model)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        raise SystemExit(f"{agent_name}: Anthropic's API rejected {KEY_NAME}. Check the key in .env. Not starting.") from None
    except anthropic.NotFoundError:
        raise SystemExit(f"{agent_name}: {KEY_NAME} works, but the API doesn't offer {model}. Not starting.") from None
    except anthropic.APIError as error:
        raise SystemExit(
            f"{agent_name}: couldn't check {KEY_NAME} with Anthropic's API ({type(error).__name__}). Not starting."
        ) from None


# ---------------------------------------------------------------------------------------------------
# The adapter: one function for all agents, two providers behind it.
# ---------------------------------------------------------------------------------------------------

async def ask_model(
    prompt: str,
    model: str,
    system: str | None = None,
    json_schema: dict | None = None,
    num_ctx: int = DEFAULT_CONTEXT_SIZE,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: float = TIMEOUT_SECONDS,
    usage: Usage | None = None,
    run_id: str | None = None,
) -> str:
    """Send one prompt (plus optional system instructions) to the model and return the answer text.

    usage: tokens, cost and time are added to it (also when the call fails after being billed).
    run_id: the A2A context id; the budget guard's per-run limit applies to it (Claude only).
    num_ctx and temperature are Ollama settings; Claude ignores them (see the module docstring).
    """
    if is_claude_model(model):
        return await _ask_claude(prompt, model, system, json_schema, timeout, usage, run_id)
    return await _ask_ollama(prompt, model, system, json_schema, num_ctx, temperature, timeout, usage)


# --- Ollama (local) ---------------------------------------------------------------------------------

def _save_debug_payload(payload: dict) -> None:
    """Debug: save the exact request sent to the model, if MODEL_DEBUG=true in .env."""
    if read_setting("MODEL_DEBUG", "false").lower() != "true":
        return
    folder = RESULTS_DIR / model_folder_name(payload["model"]) / "prompts"
    folder.mkdir(parents=True, exist_ok=True)
    file = folder / f"{datetime.now():%Y%m%d-%H%M%S-%f}.json"
    file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate: about 4 characters per token (more for German text or code)."""
    return sum(len(message["content"]) for message in messages) // 4


async def _ask_ollama(prompt, model, system, json_schema, num_ctx, temperature, timeout, usage) -> str:
    messages = []
    if system is not None:
        # System message: the standing instructions. User message: the actual input.
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": temperature},
    }
    if json_schema is not None:
        # JSON OUTPUT ENFORCED: Ollama restricts the model to text matching this schema.
        payload["format"] = json_schema

    _save_debug_payload(payload)

    # CONTEXT CHECK: Ollama silently drops text that doesn't fit into num_ctx.
    # The answer also needs room in the context, so warn well before the limit.
    estimate = _estimate_tokens(messages)
    print(f"[model_client] {model}: request ~{estimate} tokens (context {num_ctx})")
    if estimate > CONTEXT_WARNING_SHARE * num_ctx:
        print(
            f"[model_client] WARNING: request uses ~{estimate / num_ctx:.0%} of the context. "
            "The model may silently lose part of the input."
        )

    ollama_url = read_setting("OLLAMA_URL")
    # MODEL CALL: plain HTTP POST to Ollama's chat endpoint.
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{ollama_url}/api/chat", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as e:
        raise ModelError(f"Cannot reach Ollama at {ollama_url}. Is it running?") from e
    except httpx.TimeoutException as e:
        raise ModelError(f"Ollama did not answer within {timeout:g} seconds.") from e
    except httpx.HTTPStatusError as e:
        raise ModelError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}"
        ) from e

    body = response.json()
    prompt_tokens, answer_tokens = body.get("prompt_eval_count") or 0, body.get("eval_count") or 0
    if usage is not None:
        usage.add(prompt_tokens, answer_tokens, 0.0, time.perf_counter() - started)  # local: costs nothing
    # Ollama reports the real token counts, so the estimate above can be checked.
    print(f"[model_client] {model}: real prompt tokens {prompt_tokens}, answer tokens {answer_tokens}")
    return body["message"]["content"]


# --- Claude (cloud) ---------------------------------------------------------------------------------

def _split_type_lists(schema):
    """'"type": ["number", "null"]' becomes anyOf with one type each: the same meaning, in the form the SDK expects."""
    if isinstance(schema, list):
        return [_split_type_lists(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result = {key: _split_type_lists(value) for key, value in schema.items()}
    if isinstance(result.get("type"), list):
        types = result.pop("type")
        description = result.pop("description", None)
        if result:
            raise ValueError(f"Can't split a type list that has other keywords: {sorted(result)}")
        result = {"anyOf": [{"type": t} for t in types]}
        if description is not None:
            result["description"] = description
    return result


def claude_schema(schema: dict) -> dict:
    """The agent's JSON schema in the form Anthropic's structured output accepts.

    The SDK's transform_schema() keeps what the API enforces and moves the rest (here: maxItems, and
    minItems above 1) into the field's description, so the model still reads it. check_array_limits()
    checks those limits after the answer.
    """
    from anthropic import transform_schema

    return transform_schema(_split_type_lists(schema))


def check_array_limits(data, schema: dict, path: str = "answer") -> tuple[object, list[str]]:
    """Plain-Python check of minItems/maxItems from the ORIGINAL schema.

    Too many items: the extra ones are cut (Ollama's grammar can't produce them either) and a note is returned.
    Too few: ModelError, because the answer doesn't have the shape the agent needs.
    """
    notes = []
    if schema.get("type") == "object" and isinstance(data, dict):
        for key, sub_schema in schema.get("properties", {}).items():
            if key in data:
                data[key], sub_notes = check_array_limits(data[key], sub_schema, f"{path}.{key}")
                notes += sub_notes
    elif schema.get("type") == "array" and isinstance(data, list):
        max_items, min_items = schema.get("maxItems"), schema.get("minItems")
        if max_items is not None and len(data) > max_items:
            notes.append(f"{path}: {len(data)} items, cut to the schema's maximum of {max_items}")
            data = data[:max_items]
        if min_items is not None and len(data) < min_items:
            raise ModelError(f"The model's answer has {len(data)} items in {path}; the schema needs at least {min_items}.")
        item_schema = schema.get("items", {})
        for n, item in enumerate(data):
            data[n], sub_notes = check_array_limits(item, item_schema, f"{path}[{n}]")
            notes += sub_notes
    return data, notes


def _claude(timeout: float):
    """The SDK client for this agent process. The key goes to the SDK and nowhere else."""
    global _claude_client
    import anthropic

    if _claude_client is None:
        _claude_client = anthropic.AsyncAnthropic(api_key=read_setting(KEY_NAME), max_retries=2)
    return _claude_client.with_options(timeout=timeout)


async def _ask_claude(prompt, model, system, json_schema, timeout, usage, run_id) -> str:
    import anthropic

    # No temperature, no thinking setting: the model's defaults (see the module docstring).
    request = {"model": model, "max_tokens": CLAUDE_MAX_TOKENS, "messages": [{"role": "user", "content": prompt}]}
    if system is not None:
        request["system"] = system
    if json_schema is not None:
        # JSON OUTPUT ENFORCED: the API's native structured output, with the agent's (adapted) schema.
        request["output_config"] = {"format": {"type": "json_schema", "schema": claude_schema(json_schema)}}

    prompt_chars = len(prompt) + len(system or "")
    worst_case = worst_case_cost(model, prompt_chars, CLAUDE_MAX_TOKENS)
    print(f"[model_client] {model}: request ~{prompt_chars // 4} tokens (cloud, at most ${worst_case:.4f})")

    try:
        # BUDGET GUARD: checked before the call, counted right after it, under one lock.
        async with budget().paid_call(run_id or "no-run-id", worst_case) as count:
            started = time.perf_counter()
            try:
                response = await _claude(timeout).messages.create(**request)
            except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
                raise ModelError(f"Anthropic's API rejected {KEY_NAME} during the call to {model}.") from None
            except anthropic.APIError as error:
                detail = getattr(error, "message", "") or str(error)
                raise ModelError(f"The call to {model} failed: {type(error).__name__}: {detail}") from None
            seconds = time.perf_counter() - started
            # COUNTED FIRST: the call is billed whatever came back.
            u = response.usage
            cache_write, cache_read = u.cache_creation_input_tokens or 0, u.cache_read_input_tokens or 0
            input_tokens = u.input_tokens + cache_write + cache_read
            cost = call_cost(model, u.input_tokens, u.output_tokens, cache_write, cache_read)
            count(agent=_agent_name, model=model, input_tokens=input_tokens, output_tokens=u.output_tokens, usd=cost)
    except BudgetExceeded as stop:
        raise ModelError(f"The budget guard stopped the call to {model}: {stop}") from None

    if usage is not None:
        usage.add(input_tokens, u.output_tokens, cost, seconds)
    thinking = getattr(getattr(u, "output_tokens_details", None), "thinking_tokens", None)
    print(
        f"[model_client] {model}: real prompt tokens {input_tokens}, answer tokens {u.output_tokens}"
        f"{f' (thinking {thinking})' if thinking is not None else ''}, ${cost:.5f}, {seconds:.1f} s"
    )

    # A response can begin with thinking blocks; only a finished answer is usable.
    if response.stop_reason != "end_turn":
        raise ModelError(f"{model} stopped with '{response.stop_reason}', so there is no complete answer to use.")
    text = "".join(block.text for block in response.content if block.type == "text")

    if json_schema is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text  # the agent reports invalid JSON in its own words
        data, notes = check_array_limits(data, json_schema)
        for note in notes:
            print(f"[model_client] {model}: {note}")
        if usage is not None:
            usage.notes += notes
        text = json.dumps(data, ensure_ascii=False)
    return text
