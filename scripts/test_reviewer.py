"""Review an existing pipeline run with the Application Reviewer, without rerunning the pipeline.

Run with:  python scripts/test_reviewer.py results/runs/<date-time> [cv.pdf]
(the Application Reviewer must be running on port 9004)

The CV is taken from samples/cvs/<name in run_log.json>, unless you pass a path.
Saves review.json and review.md into the run folder (overwriting an earlier review).
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text, get_text_parts, new_data_part, new_raw_part, new_text_part
from a2a.types import Message, Role, SendMessageRequest, TaskState

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


async def main(run_dir: Path, cv_file: Path | None) -> None:
    requirements = json.loads((run_dir / "requirements.json").read_text(encoding="utf-8"))
    report = json.loads((run_dir / "match_report.json").read_text(encoding="utf-8"))
    letter = (run_dir / "cover_letter.md").read_text(encoding="utf-8")
    if cv_file is None:
        cv_name = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))["inputs"]["cv"]
        cv_file = PROJECT_ROOT / "samples" / "cvs" / cv_name
    if not cv_file.is_file():
        sys.exit(f"CV not found: {cv_file} (pass the CV path as the second argument)")

    async with httpx.AsyncClient(timeout=600, event_hooks={"response": [save_raw_response]}) as http:
        # AGENT CARD: fetch it, then build a client from it.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        print(f"Agent card: {card.name} {card.version}")
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        # MESSAGE with four PARTS: requirements and report (DATA), the letter (TEXT), the CV (FILE).
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[
                new_data_part(requirements, media_type="application/json"),
                new_data_part(report, media_type="application/json"),
                new_text_part(letter),
                new_raw_part(cv_file.read_bytes(), media_type="application/pdf", filename=cv_file.name),
            ],
        )
        print(f"Reviewing {run_dir.name} ... (one model call, may take a minute)")
        start = time.perf_counter()
        async for response in client.send_message(SendMessageRequest(message=message)):
            task = response.task
        print(f"Task status: {TaskState.Name(task.status.state)}   ({time.perf_counter() - start:.1f} s)")

    print("\n----- Raw JSON-RPC response -----")
    print(json.dumps(shorten(raw_responses[-1]), indent=2, ensure_ascii=False))
    print("-----\n")

    if task.status.state != TaskState.TASK_STATE_COMPLETED:
        print(f"Status message: {get_message_text(task.status.message)}")
        return

    # ARTIFACT: the review as a DATA part and as readable Markdown (TEXT part).
    parts = task.artifacts[0].parts
    review, review_md = get_data_parts(parts)[0], get_text_parts(parts)[0]
    print(review_md)
    dropped = {k: int(v) for k, v in review['dropped_ungrounded'].items()}
    print(f"Dropped as ungrounded (quote not in the letter): {dropped}")
    (run_dir / "review.json").write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "review.md").write_text(review_md, encoding="utf-8")
    print(f"Saved review.json and review.md in {run_dir}")


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("Usage: python scripts/test_reviewer.py <run-folder> [cv.pdf]")
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) == 3 else None))
