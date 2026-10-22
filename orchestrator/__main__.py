"""Orchestrator: runs the whole pipeline with one command.

Fixed routing: Job Analyst -> CV Matcher -> Cover Letter Writer (see pipeline.py).

Run with:  python -m orchestrator samples/job_ad_1.txt samples/cvs/my_cv.pdf
(start the agents first:  python scripts/start_agents.py)
"""

import asyncio
import sys
import uuid
from pathlib import Path

import httpx

from orchestrator.agent_runner import read_agent_cards, run_step
from orchestrator.pipeline import STEPS
from orchestrator.run_store import RunStore

HTTP_TIMEOUT_SECONDS = 900  # the slowest agent call (letter + rewrite) can take a few minutes


async def run(job_ad_file: Path, cv_file: Path) -> int:
    for path in (job_ad_file, cv_file):
        if not path.is_file():
            print(f"File not found: {path}")
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

        run_store = RunStore(context_id, {"job_ad": job_ad_file.name, "cv": cv_file.name})
        print(f"Run {run_store.relative_dir}  (context {context_id})\n")

        # PIPELINE STEPS: always the same order; each step gets the results of the ones before.
        for agent in agents:
            result = await run_step(agent, agent.step.build_parts(results), context_id)
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
    report = results.get("match_report", {})
    details = results.get("letter_details", {})
    print(f"\n✓ Done. Everything is saved in {run_store.relative_dir}/")
    if report:
        print(f"  Match score: {report['score_percent']:g}%  ({report['summary'].split('.')[0]}.)")
    if details:
        print(f"  Cover letter: {run_store.relative_dir}/cover_letter.md  ({details['word_count']:g} words)")
        print(f"  Unproven claims to review: {len(details['unproven_claims'])}")
        for warning in details["style_warnings"]:
            print(f"  Style warning: {warning}")


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python -m orchestrator <job_ad.txt> <cv.pdf>")
    try:
        sys.exit(asyncio.run(run(Path(sys.argv[1]), Path(sys.argv[2]))))
    except KeyboardInterrupt:
        sys.exit("\nStopped by you (Ctrl+C).")


if __name__ == "__main__":
    main()
