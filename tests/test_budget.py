"""The budget guard (agents/budget.py): prices, limits, and safe writes from several processes at once."""

import asyncio
import json
import multiprocessing

import pytest

from agents.budget import Budget, BudgetExceeded, call_cost, has_price, worst_case_cost

MODEL = "claude-haiku-5-5"


def test_haiku_prices_short_and_long_prompts():
    # Up to 100,000 prompt tokens: $0.10 per million in, $0.50 per million out.
    assert call_cost(MODEL, 10_000, 1_000) == pytest.approx((0.10 * 10_000 + 0.50 * 1_000) / 1_000_000)
    # Over 100,000 prompt tokens, the whole call is billed at the long-prompt rates.
    assert call_cost(MODEL, 100_001, 1_000) == pytest.approx((0.50 * 100_001 + 2.50 * 1_000) / 1_000_000)


def test_cache_tokens_are_billed_and_count_towards_prompt_length():
    cost = call_cost(MODEL, 1_000, 0, cache_write=1_000, cache_read=1_000)
    assert cost == pytest.approx(0.10 * (1_000 + 1.25 * 1_000 + 0.1 * 1_000) / 1_000_000)


def test_worst_case_is_never_below_a_realistic_call():
    prompt_chars, max_out = 20_000, 16_000
    realistic = call_cost(MODEL, prompt_chars // 4, 2_000)
    assert worst_case_cost(MODEL, prompt_chars, max_out) > realistic


def test_only_priced_models_are_known():
    assert has_price(MODEL)
    assert not has_price("claude-some-unknown-model")


def spend(budget: Budget, run: str, usd: float, worst: float = 0.0) -> None:
    async def one_call():
        async with budget.paid_call(run, worst) as count:
            count(agent="test", model=MODEL, input_tokens=10, output_tokens=5, usd=usd)
    asyncio.run(one_call())


def test_calls_are_counted_per_run_and_in_total(tmp_path):
    budget = Budget(tmp_path / "spend.json", run_limit=0.5, total_limit=3.0)
    spend(budget, "run-a", 0.10)
    spend(budget, "run-a", 0.05)
    spend(budget, "run-b", 0.20)
    assert budget.spent("run-a") == (pytest.approx(0.15), pytest.approx(0.35))
    ledger = json.loads((tmp_path / "spend.json").read_text())
    assert ledger["runs"]["run-a"]["calls"] == 2
    assert len(ledger["calls"]) == 3


def test_a_call_that_could_pass_the_run_limit_is_not_made(tmp_path):
    budget = Budget(tmp_path / "spend.json", run_limit=0.5, total_limit=3.0)
    spend(budget, "run-a", 0.45)
    with pytest.raises(BudgetExceeded, match="limit per run"):
        spend(budget, "run-a", 0.01, worst=0.06)
    spend(budget, "run-b", 0.01, worst=0.06)  # another run still has room


def test_a_call_that_could_pass_the_total_limit_is_not_made(tmp_path):
    budget = Budget(tmp_path / "spend.json", run_limit=0.5, total_limit=1.0)
    for n in range(3):
        spend(budget, f"run-{n}", 0.30)
    with pytest.raises(BudgetExceeded, match="total limit"):
        spend(budget, "run-new", 0.01, worst=0.2)


def test_a_failed_call_costs_nothing(tmp_path):
    budget = Budget(tmp_path / "spend.json", run_limit=0.5, total_limit=3.0)

    async def failing_call():
        async with budget.paid_call("run-a", 0.01):
            raise RuntimeError("the API call failed")

    with pytest.raises(RuntimeError):
        asyncio.run(failing_call())
    assert budget.spent("run-a") == (0.0, 0.0)


def _spend_many(path, worker: int, calls: int) -> None:
    """Runs in a separate process, like one agent."""
    budget = Budget(path, run_limit=100.0, total_limit=100.0)
    for _ in range(calls):
        spend(budget, f"run-{worker % 2}", 0.001)


def test_four_processes_writing_at_once_lose_nothing(tmp_path):
    path = tmp_path / "spend.json"
    workers, calls = 4, 25
    processes = [
        multiprocessing.get_context("spawn").Process(target=_spend_many, args=(path, w, calls))
        for w in range(workers)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=60)
        assert p.exitcode == 0
    ledger = json.loads(path.read_text())
    assert len(ledger["calls"]) == workers * calls
    assert ledger["total_usd"] == pytest.approx(workers * calls * 0.001)
    assert sum(run["calls"] for run in ledger["runs"].values()) == workers * calls


def test_sonnet_has_one_rate_card_and_its_own_cache_rate():
    sonnet = "claude-sonnet-5-5"
    assert has_price(sonnet)
    assert call_cost(sonnet, 10_000, 1_000) == pytest.approx((2.00 * 10_000 + 10.00 * 1_000) / 1_000_000)
    # No long-prompt surcharge: 200,000 tokens cost the same per token as 10,000.
    assert call_cost(sonnet, 200_000, 0) == pytest.approx(2.00 * 200_000 / 1_000_000)
    assert call_cost(sonnet, 0, 0, cache_read=1_000_000) == pytest.approx(2.00 * 0.05)
