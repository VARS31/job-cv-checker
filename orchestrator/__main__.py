"""Orchestrator: runs the whole pipeline with one command.

Fixed routing: Job Analyst -> CV Matcher -> Cover Letter Writer -> Application Reviewer
(see pipeline.py).

Run with:  python -m orchestrator samples/job_ad_1.txt samples/cvs/my_cv.pdf
           python -m orchestrator <ad> <cv> --answers samples/demo/answers_demo.json   (scripted answers)
(start the agents first:  python scripts/start_agents.py)
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import httpx

from orchestrator.agent_runner import read_agent_cards, run_step
from orchestrator.answers import load_answers
from orchestrator.pipeline import STEPS
from orchestrator.run_store import RunStore

HTTP_TIMEOUT_SECONDS = 900  # the slowest agent call (letter + rewrite) can take a few minutes


async def run(job_ad_file: Path, cv_file: Path, answers_file: Path | None = None) -> int:
    for path in (job_ad_file, cv_file):
        if not path.is_file():
            print(f"File not found: {path}")
            return 1
    try:
        answers = load_answers(answers_file)  # ANSWERS: from you in the terminal, or from a file
    except ValueError as error:
        print(error)
        return 1

    # Everything the steps may use; each step adds its own results.
    results = {
        "job_ad": job_ad_file.read_text(encoding="utf-8"),
        "cv_pdf": cv_file.read_bytes(),
        "cv_filename": cv_file.name,
    }
    context_id = str(uuid.uuid4())  # one context id for the whole run, across all agents

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as http:
        # AGENT CARDS READ: fail fast, before any work, if an agent is not running.
        agents = await read_agent_cards(STEPS, http)
        if agents is None:
            return 1

        inputs = {"job_ad": job_ad_file.name, "cv": cv_file.name, "answers": str(answers_file) if answers_file else "terminal"}
        run_store = RunStore(context_id, inputs)
        print(f"Run {run_store.relative_dir}  (context {context_id})")
        print(f"Answers: {'from ' + str(answers_file) if answers_file else 'you, in this terminal'}\n")

        # PIPELINE STEPS: always the same order; each step gets the results of the ones before.
        for agent in agents:
            result = await run_step(agent, agent.step.build_parts(results), context_id, answers)
            if result.state == "completed":
                try:
                    results.update(agent.step.read_artifacts(result.artifacts))
                except ValueError as error:
                    result.state, result.error = "error", f"Unexpected artifact: {error}"
            run_store.add_step(result)

            if result.state != "completed":
                # FAILURE HANDLED: print the reason, keep what is finished, stop.
                print(f"\n✗ {agent.step.name} stopped ({result.state}): {result.error}")
                run_store.finish("stopped", f"{agent.step.name}: {result.error}")
                print(f"Finished steps are saved in {run_store.relative_dir}/")
                return 1

            # RUN SAVED: this step's outputs, right away.
            run_store.save_outputs(agent.step, results)

    run_store.finish("completed")
    print_summary(results, run_store)
    return 0


def print_summary(results: dict, run_store: RunStore) -> None:
    print(f"\n✓ Done. Everything is saved in {run_store.relative_dir}/")
    for step in STEPS:  # each step decides what it wants to show
        for line in step.summary(results):
            print(f"  {line}")
    totals = run_store.log["totals"]
    cost = f"${totals['cost_usd']:.4f} (cloud)" if totals["cost_usd"] else "$0 (all local)"
    print(f"  Model cost: {cost}, {totals['input_tokens']} tokens in, {totals['output_tokens']} out")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m orchestrator", description="Run the whole pipeline.")
    parser.add_argument("job_ad", type=Path, help="the job ad as a .txt file")
    parser.add_argument("cv", type=Path, help="the CV as a PDF with selectable text")
    parser.add_argument(
        "--answers", type=Path, metavar="FILE",
        help="JSON file with scripted answers to the agents' questions (see orchestrator/answers.py)",
    )
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(run(args.job_ad, args.cv, args.answers)))
    except KeyboardInterrupt:
        sys.exit("\nStopped by you (Ctrl+C).")


if __name__ == "__main__":
    main()
