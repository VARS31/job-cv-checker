"""Review an existing pipeline run with the Application Reviewer, without rerunning the pipeline.

Run with:  python -m scripts.try_reviewer results/runs/<date-time> [cv.pdf]
           python -m scripts.try_reviewer <run> <cv.pdf> --letter other_letter.md --out results/reviews/x
(the Application Reviewer must be running on port 9004)

The CV is taken from samples/cvs/<name in run_log.json>, unless you pass a path.
The job ad is the run's job_ad.txt (runs made before 2026-11-09 don't have one: pass --job-ad).
--letter reviews another letter with the same requirements, report, ad and CV (e.g. one with planted errors).
Saves review.json and review.md into --out (default: the run folder, overwriting an earlier review).
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text, get_text_parts, new_data_part, new_raw_part
from a2a.types import Message, Role, SendMessageRequest, TaskState

from orchestrator.agent_runner import StepResult, _add_usage, _usage_from
from orchestrator.pipeline import labelled_text

AGENT_URL = "http://localhost:9004"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

raw_responses = []


async def save_raw_response(response: httpx.Response) -> None:
    """httpx hook: keep the exact JSON the server sent for each POST."""
    if response.request.method == "POST":
        await response.aread()
        raw_responses.append(response.json())


def shorten(value):
    """Cut the base64 PDF so the printout stays readable."""
    if isinstance(value, dict):
        return {k: (f"{v[:40]}... ({len(v)} chars)" if k == "raw" and isinstance(v, str) and len(v) > 60 else shorten(v))
                for k, v in value.items()}
    if isinstance(value, list):
        return [shorten(v) for v in value]
    return value


async def main(run_dir: Path, cv_file: Path | None, letter_file: Path | None, job_ad_file: Path | None,
               out_dir: Path | None, show_raw: bool) -> None:
    requirements = json.loads((run_dir / "requirements.json").read_text(encoding="utf-8"))
    report = json.loads((run_dir / "match_report.json").read_text(encoding="utf-8"))
    letter = (letter_file or run_dir / "cover_letter.md").read_text(encoding="utf-8")
    job_ad_file = job_ad_file or run_dir / "job_ad.txt"
    if not job_ad_file.is_file():
        sys.exit(f"Job ad not found: {job_ad_file} (pass it with --job-ad)")
    job_ad = job_ad_file.read_text(encoding="utf-8")
    if cv_file is None:
        cv_name = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))["inputs"]["cv"]
        cv_file = PROJECT_ROOT / "samples" / "cvs" / cv_name
    if not cv_file.is_file():
        sys.exit(f"CV not found: {cv_file} (pass the CV path as the second argument)")
    out_dir = out_dir or run_dir

    async with httpx.AsyncClient(timeout=600, event_hooks={"response": [save_raw_response]}) as http:
        # AGENT CARD: fetch it, then build a client from it.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        print(f"Agent card: {card.name} {card.version}")
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        # MESSAGE with five PARTS: requirements and report (DATA), the letter and the ad (TEXT, labelled), the CV (FILE).
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[
                new_data_part(requirements, media_type="application/json"),
                new_data_part(report, media_type="application/json"),
                labelled_text(letter, "cover_letter"),
                labelled_text(job_ad, "job_ad"),
                new_raw_part(cv_file.read_bytes(), media_type="application/pdf", filename=cv_file.name),
            ],
        )
        print(f"Reviewing {letter_file or run_dir.name} ... (one model call, may take a minute)")
        start = time.perf_counter()
        async for response in client.send_message(SendMessageRequest(message=message)):
            task = response.task
        seconds = time.perf_counter() - start
        print(f"Task status: {TaskState.Name(task.status.state)}   ({seconds:.1f} s)")

    if show_raw:
        print("\n----- Raw JSON-RPC response -----")
        print(json.dumps(shorten(raw_responses[-1]), indent=2, ensure_ascii=False))
        print("-----\n")

    # USAGE: the model the Reviewer used, as it reports it.
    usage = StepResult(agent=card.name, url=AGENT_URL, agent_version=card.version)
    _add_usage(usage, _usage_from(task))
    print(f"Model: {usage.model}   tokens in {usage.input_tokens}, out {usage.output_tokens}   ${usage.cost_usd:.4f}")

    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        print(f"Status message: {get_message_text(task.status.message)}")
        return

    # ARTIFACT: the review as a DATA part and as readable Markdown (TEXT part).
    parts = task.artifacts[0].parts
    review, review_md = get_data_parts(parts)[0], get_text_parts(parts)[0]
    print(review_md)
    dropped = {k: int(v) for k, v in review['dropped_ungrounded'].items()}
    print(f"Dropped as ungrounded (quote not in the letter): {dropped}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "review.md").write_text(review_md, encoding="utf-8")
    print(f"Saved review.json and review.md in {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Review an existing run with the Application Reviewer.")
    parser.add_argument("run_dir", type=Path, help="a folder in results/runs/")
    parser.add_argument("cv", type=Path, nargs="?", help="the CV PDF (default: samples/cvs/<name in run_log.json>)")
    parser.add_argument("--letter", type=Path, help="review this letter instead of the run's cover_letter.md")
    parser.add_argument("--job-ad", type=Path, help="the job ad text (default: the run's job_ad.txt)")
    parser.add_argument("--out", type=Path, help="where to save review.json and review.md (default: the run folder)")
    parser.add_argument("--raw", action="store_true", help="also print the raw JSON-RPC response")
    args = parser.parse_args()
    asyncio.run(main(args.run_dir, args.cv, args.letter, args.job_ad, args.out, args.raw))
