"""Test the Cover Letter Writer: send requirements + match report + CV, answer its question,
print the letter and the checked claims.

Run with:
  python scripts/test_cover_letter.py results/ministral-3_8b/job_ad_1.json \
      results/cv_matcher/job_ad_1__my_cv.json samples/cvs/my_cv.pdf
(the Cover Letter Writer must be running on port 9003)
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

AGENT_URL = "http://localhost:9003"

raw_responses = []


async def save_raw_response(response: httpx.Response) -> None:
    """httpx hook: keep the exact JSON the server sent for each POST."""
    if response.request.method == "POST":
        await response.aread()
        raw_responses.append(response.json())


def shorten(value):
    """Cut the base64 PDF and the saved CV text so the printout stays readable."""
    if isinstance(value, dict):
        return {
            k: (f"{v[:40]}... ({len(v)} chars)" if k in ("raw", "cv_text") and isinstance(v, str) and len(v) > 60 else shorten(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [shorten(v) for v in value]
    return value


def print_raw_step(step: str) -> None:
    print(f"\n----- Raw JSON-RPC response ({step}) -----")
    print(json.dumps(shorten(raw_responses[-1]), indent=2, ensure_ascii=False))
    print("-----")


async def send(client, message: Message):
    start = time.perf_counter()
    async for response in client.send_message(SendMessageRequest(message=message)):
        task = response.task
    print(f"\nTask status: {TaskState.Name(task.status.state)}   ({time.perf_counter() - start:.1f} s)")
    return task


def print_result(letter: str, details: dict) -> None:
    print(f"\n===== Cover letter (Cover Letter Writer {details.get('agent_version', 'unknown')}) =====\n")
    print(letter)
    print(f"\n({details['word_count']:g} words, {details['body_paragraphs']:g} body paragraphs)")

    print("\nClaims with proof:")
    for c in details["claims"]:
        print(f"  + [{c['source']}] {c['claim']}\n      \"{c['quote']}\"")
    if details["rewrite_used"]:
        print("\nRewrite used. Claims removed because they had no valid proof:")
        for c in details["removed_in_rewrite"]:
            print(f"  - {c['claim']}   ({c['problem']})")
    print("\nUnproven claims still in the letter (please review):")
    for c in details["unproven_claims"] or [{"claim": "none", "problem": ""}]:
        print(f"  ! {c['claim']}" + (f"   ({c['problem']}: \"{c['quote']}\")" if c["problem"] else ""))
    print("\nStyle warnings:")
    for w in details["style_warnings"] or ["none"]:
        print(f"  ~ {w}")


async def main(requirements_file: Path, report_file: Path, cv_file: Path) -> None:
    result = json.loads(requirements_file.read_text(encoding="utf-8"))
    requirements = result.get("requirements", result)  # run_all_samples file or plain JSON
    report = json.loads(report_file.read_text(encoding="utf-8"))

    async with httpx.AsyncClient(timeout=700, event_hooks={"response": [save_raw_response]}) as http:
        # AGENT CARD: fetch it, then build a client from it.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        print(f"Agent card: {card.name} {card.version} - output modes {list(card.default_output_modes)}")
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        # MESSAGE with three PARTS: requirements and report as DATA parts, the CV as a FILE part.
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[
                new_data_part(requirements, media_type="application/json"),
                new_data_part(report, media_type="application/json"),
                new_raw_part(cv_file.read_bytes(), media_type="application/pdf", filename=cv_file.name),
            ],
        )
        task = await send(client, message)
        print_raw_step("first message")

        # INPUT-REQUIRED: one free-text question in the status message.
        while task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            print(f"\n{get_message_text(task.status.message)}")
            answer = input("> ").strip()
            # Same TASK id and context id -> the agent continues the paused task.
            reply = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                task_id=task.id,
                context_id=task.context_id,
                parts=[new_text_part(answer)],
            )
            print("Writing the letter ... (one or two model calls, may take a minute or two)")
            task = await send(client, reply)
            print_raw_step("answer")

        if task.status.state == TaskState.TASK_STATE_COMPLETED:
            # ARTIFACT: the letter as a TEXT part, the claims as a DATA part.
            parts = task.artifacts[0].parts
            print_result(get_text_parts(parts)[0], get_data_parts(parts)[0])
        elif task.status.HasField("message"):
            print(f"Status message: {get_message_text(task.status.message)}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("Usage: python scripts/test_cover_letter.py <requirements.json> <cv_matcher_report.json> <cv.pdf>")
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
