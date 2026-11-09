"""The budget guard for paid (cloud) model calls.

Real usage is counted after every call, and the running totals are kept in one file on disk
(results/cloud_spend.json, gitignored), so the limits hold across runs and restarts.
A call that could take its run or the total past a limit isn't made.

Four agent processes share the file, so paid calls take turns: a lock (fcntl.flock on a separate
lock file) is held from the check, through the call, until its cost is written. The pipeline calls
one agent at a time anyway, so in practice nobody waits. The file is replaced in one step, so
stopping at any moment can't leave half a ledger.

Local models cost nothing and never come through here. Nothing about the API key reaches this file.
"""

import asyncio
import fcntl
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

# Dollars per million tokens (input, output). Source: platform.claude.com/docs/en/about-claude/pricing.
# Output tokens include the model's thinking. We don't use caching, but a cached token would be billed,
# so cache writes and reads are counted (as a multiple of the input rate).
# - Claude Haiku 5.5 (checked 2026-11-08): two rate cards, chosen by prompt length; a prompt's length
#   counts all its input tokens, cached ones included.
# - Claude Sonnet 5.5 (checked 2026-11-09): one rate card for the whole context window.
PRICES = {
    "claude-haiku-5-5": {
        "long_prompt_above": 100_000, "short": (0.10, 0.50), "long": (0.50, 2.50),
        "cache_write": 1.25, "cache_read": 0.1,
    },
    "claude-sonnet-5-5": {
        "long_prompt_above": None, "short": (2.00, 10.00), "long": (2.00, 10.00),
        "cache_write": 1.25, "cache_read": 0.05,
    },
}
WORST_CASE_CHARS_PER_TOKEN = 2  # a token is never less than half a character, so this over-estimates


class BudgetExceeded(Exception):
    """A paid call was not made, because it could have passed a limit."""


def has_price(model: str) -> bool:
    return model in PRICES


def call_cost(model: str, input_tokens: int, output_tokens: int, cache_write: int = 0, cache_read: int = 0) -> float:
    """What one call costs in dollars."""
    price = PRICES[model]
    prompt_tokens = input_tokens + cache_write + cache_read
    threshold = price["long_prompt_above"]
    per_input, per_output = price["short"] if threshold is None or prompt_tokens <= threshold else price["long"]
    billed_input = input_tokens + price["cache_write"] * cache_write + price["cache_read"] * cache_read
    return (per_input * billed_input + per_output * output_tokens) / 1_000_000


def worst_case_cost(model: str, prompt_chars: int, max_output_tokens: int) -> float:
    """The most the next call can cost: the prompt at its largest possible token count, and every output token used."""
    return call_cost(model, prompt_chars // WORST_CASE_CHARS_PER_TOKEN + 1, max_output_tokens)


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Budget:
    def __init__(self, path: Path, run_limit: float, total_limit: float) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.run_limit, self.total_limit = run_limit, total_limit

    def _ledger(self) -> dict:
        if not self.path.exists():
            return {"total_usd": 0.0, "runs": {}, "calls": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def spent(self, run_id: str | None = None) -> tuple[float, float]:
        """(this run, everything in the file), in dollars."""
        ledger = self._ledger()
        return ledger["runs"].get(run_id, {}).get("usd", 0.0), ledger["total_usd"]

    def check(self, run_id: str, next_call_at_most: float) -> None:
        """Raises BudgetExceeded if the next call could take this run or the total past its limit."""
        run, total = self.spent(run_id)
        if run + next_call_at_most > self.run_limit:
            raise BudgetExceeded(
                f"this run has spent ${run:.4f} and the next call could cost up to ${next_call_at_most:.4f}; "
                f"the limit per run is ${self.run_limit:.2f}"
            )
        if total + next_call_at_most > self.total_limit:
            raise BudgetExceeded(
                f"all cloud calls together have spent ${total:.4f} and the next call could cost up to "
                f"${next_call_at_most:.4f}; the total limit is ${self.total_limit:.2f}"
            )

    def _add(self, run_id: str, agent: str, model: str, input_tokens: int, output_tokens: int, usd: float) -> None:
        """Count one finished call. Only called while the lock is held."""
        ledger = self._ledger()
        run = ledger["runs"].setdefault(
            run_id, {"usd": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0, "first_call": _now()}
        )
        run["usd"] = round(run["usd"] + usd, 8)
        run["calls"] += 1
        run["input_tokens"] += input_tokens
        run["output_tokens"] += output_tokens
        ledger["total_usd"] = round(ledger["total_usd"] + usd, 8)
        ledger["calls"].append({
            "time": _now(), "run": run_id, "agent": agent, "model": model,
            "input_tokens": input_tokens, "output_tokens": output_tokens, "usd": round(usd, 8),
        })
        # WRITE SAFELY: write a temporary file, then swap it in with one atomic rename.
        temporary = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    @asynccontextmanager
    async def paid_call(self, run_id: str, worst_case_usd: float):
        """Use around one paid call:

            async with budget.paid_call(run_id, worst_case) as count:
                response = ...the call...
                count(agent=..., model=..., input_tokens=..., output_tokens=..., usd=...)

        Waits for the lock without blocking the agent's event loop, checks the limits (raising
        BudgetExceeded before any call), and keeps the lock until the call has been counted.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.lock_path, "a") as lock:
            await asyncio.to_thread(fcntl.flock, lock, fcntl.LOCK_EX)
            try:
                self.check(run_id, worst_case_usd)
                yield lambda **usage: self._add(run_id, **usage)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
