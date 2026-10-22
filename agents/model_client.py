"""The one place where the project talks to a model (local Ollama).

All model calls in the project must go through ask_model().
"""

import json
import os
from datetime import datetime
from pathlib import Path

import httpx

OLLAMA_URL = "http://localhost:11434"
DEFAULT_CONTEXT_SIZE = 8192  # tokens
DEFAULT_TEMPERATURE = 0.0  # 0 = always pick the most likely word: steady, repeatable output
TIMEOUT_SECONDS = 120  # small local models can be slow, especially on first load
CONTEXT_WARNING_SHARE = 0.8  # warn when a request fills more than 80% of the context

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RESULTS_DIR = PROJECT_ROOT / "results"


class ModelError(Exception):
    """Raised when the model can't be reached or returns an error."""


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


async def ask_model(
    prompt: str,
    model: str,
    system: str | None = None,
    json_schema: dict | None = None,
    num_ctx: int = DEFAULT_CONTEXT_SIZE,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: float = TIMEOUT_SECONDS,
) -> str:
    """Send one prompt (plus optional system instructions) to Ollama and return the answer."""
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

    # MODEL CALL: plain HTTP POST to Ollama's chat endpoint.
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{OLLAMA_URL}/api/chat", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as e:
        raise ModelError(f"Cannot reach Ollama at {OLLAMA_URL}. Is it running?") from e
    except httpx.TimeoutException as e:
        raise ModelError(f"Ollama did not answer within {timeout:g} seconds.") from e
    except httpx.HTTPStatusError as e:
        raise ModelError(
            f"Ollama returned HTTP {e.response.status_code}: {e.response.text}"
        ) from e

    body = response.json()
    # Ollama reports the real token counts, so the estimate above can be checked.
    print(
        f"[model_client] {model}: real prompt tokens {body.get('prompt_eval_count')}, "
        f"answer tokens {body.get('eval_count')}"
    )
    return body["message"]["content"]
