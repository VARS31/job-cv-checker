"""Orchestrator: runs the whole pipeline with one command.

Fixed routing: Job Analyst -> CV Matcher -> Cover Letter Writer -> Application Reviewer
(see pipeline.py).

Run with:  python -m orchestrator samples/job_ad_1.txt samples/cvs/my_cv.pdf
           python -m orchestrator <ad> <cv> --answers samples/demo/answers_demo.json   (scripted answers)
(start the agents first:  python scripts/start_agents.py, or in Docker: python scripts/docker_up.py)

With TRACING=on, the run becomes one trace across all agents (docs/observability.md); the links are
printed at the end.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import httpx

from agents import tracing
from orchestrator.agent_runner import read_agent_cards, run_step
from orchestrator.answers import load_answers
from orchestrator.pipeline import STEPS
from orchestrator.run_store import RunStore

HTTP_TIMEOUT_SECONDS = 900  # the slowest agent call (letter + rewrite) can take a few minutes
DEMO_DIR = Path(__file__).resolve().parent.parent / "samples" / "demo"  # the fictional CVs


def is_demo_cv(cv_file: Path) -> bool:
    """True for the fictional CVs in samples/demo/: the only ones whose text may go into a trace."""
    return cv_file.resolve().is_relative_to(DEMO_DIR.resolve())


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

    # TRACING (off by default): one trace for the whole run. Content (prompts, CV text, letters) only
    # with TRACE_CONTENT=on, and only for the fictional demo CVs.
    tracing.setup("orchestrator")
    if tracing.content_switch():
        if not is_demo_cv(cv_file):
            print("TRACE_CONTENT is on, which would put the prompts, the CV text and the letter into the trace. "
                  "That's only allowed with the fictional CVs in samples/demo/. Turn TRACE_CONTENT off, "
                  "or use a demo CV.")
            return 1
        print("Content recording is on: prompts, CV text and letters go into the trace (demo CV).")
        with tracing.allow_content():  # the permission travels to the agents as baggage
            return await traced_run(job_ad_file, cv_file, answers_file, answers)
    return await traced_run(job_ad_file, cv_file, answers_file, answers)


async def traced_run(job_ad_file: Path, cv_file: Path, answers_file: Path | None, answers) -> int:
    """The run inside its ROOT SPAN; then the trace is sent and its links printed."""
    with tracing.span("pipeline run", {
        "openinference.span.kind": "CHAIN",
        "cvchecker.steps": len(STEPS),
        "cvchecker.answers_from": answers.source,
    }) as root:
        tracing.set_content(root, {"cvchecker.job_ad_file": job_ad_file.name, "cvchecker.cv_file": cv_file.name})
        code = await pipeline(job_ad_file, cv_file, answers_file, answers, root)
    trace_id = tracing.trace_id_of(root)
    tracing.shutdown()  # send the trace before saying where to find it
    for line in tracing.trace_links(trace_id):
        print(line)
    return code


async def pipeline(job_ad_file: Path, cv_file: Path, answers_file: Path | None, answers, root) -> int:
    # Everything the steps may use; each step adds its own results.
    results = {
        "job_ad": job_ad_file.read_text(encoding="utf-8"),
        "cv_pdf": cv_file.read_bytes(),
        "cv_filename": cv_file.name,
    }
    context_id = str(uuid.uuid4())  # one context id for the whole run, across all agents

    # TRACE CONTEXT: with tracing on, every request to an agent carries the trace context in its headers.
    hooks = {"request": [tracing.inject_headers]} if tracing.enabled() else None
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, event_hooks=hooks) as http:
        # AGENT CARDS READ: fail fast, before any work, if an agent is not running.
        agents = await read_agent_cards(STEPS, http)
        if agents is None:
            return 1

        inputs = {"job_ad": job_ad_file.name, "cv": cv_file.name, "answers": str(answers_file) if answers_file else "terminal"}
        run_store = RunStore(context_id, inputs, tracing.trace_id_of(root))
        run_store.save_text("job_ad.txt", results["job_ad"])  # so the run can be reviewed again later
        tracing.set_attributes(root, {"cvchecker.run_dir": run_store.relative_dir, "a2a.context.id": context_id})
        print(f"Run {run_store.relative_dir}  (context {context_id})")
        print(f"Answers: {'from ' + str(answers_file) if answers_file else 'you, in this terminal'}\n")

        # PIPELINE STEPS: always the same order; each step gets the results of the ones before.
        for number, agent in enumerate(agents, start=1):
            # SPAN per step; inside it, the A2A client span and (in the agent) the server span.
            with tracing.span(f"step {number}: {agent.step.name}", {
                "openinference.span.kind": "CHAIN",
                "cvchecker.agent": agent.step.name,
                "cvchecker.agent.version": agent.card.version,
                "cvchecker.agent.url": agent.url,
            }) as step_span:
                result = await run_step(agent, agent.step.build_parts(results), context_id, answers)
                if result.state == "completed":
                    try:
                        results.update(agent.step.read_artifacts(result.artifacts))
                    except ValueError as error:
                        result.state, result.error = "error", f"Unexpected artifact: {error}"
                run_store.add_step(result)
                describe_step(step_span, result)

                if result.state != "completed":
                    # FAILURE HANDLED: print the reason, keep what is finished, stop.
                    print(f"\n✗ {agent.step.name} stopped ({result.state}): {result.error}")
                    run_store.finish("stopped", f"{agent.step.name}: {result.error}")
                    tracing.mark_error(root, f"{agent.step.name}: {result.error}")
                    print(f"Finished steps are saved in {run_store.relative_dir}/")
                    return 1

                # RUN SAVED: this step's outputs, right away.
                run_store.save_outputs(agent.step, results)

    run_store.finish("completed")
    totals = run_store.log["totals"]
    tracing.set_attributes(root, {
        "cvchecker.status": "completed",
        "cvchecker.cost_usd": totals["cost_usd"],
        "cvchecker.input_tokens": totals["input_tokens"],
        "cvchecker.output_tokens": totals["output_tokens"],
    })
    print_summary(results, run_store)
    return 0


def describe_step(span, result) -> None:
    """What a step's span records: the agent's own report (model, tokens, cost) and how it ended."""
    tracing.set_attributes(span, {
        "cvchecker.step.state": result.state,
        "a2a.task.id": result.task_id,
        "cvchecker.model": result.model,
        "cvchecker.input_tokens": result.input_tokens,
        "cvchecker.output_tokens": result.output_tokens,
        "cvchecker.cost_usd": result.cost_usd,
        "cvchecker.input_rounds": result.input_rounds,
        "cvchecker.agent_seconds": round(result.seconds, 2),
    })
    if result.state != "completed":
        tracing.mark_error(span, result.error or result.state)


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
