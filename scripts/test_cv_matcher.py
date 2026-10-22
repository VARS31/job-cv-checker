"""Test the CV Matcher: send requirements + a CV, answer its questions, print the report.

Run with:  python scripts/test_cv_matcher.py results/ministral-3_8b/job_ad_1.json samples/cvs/cv_vyron.pdf
(the CV Matcher must be running on port 9002)
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text, new_data_part, new_raw_part
from a2a.types import Message, Role, SendMessageRequest, TaskState

AGENT_URL = "http://localhost:9002"

raw_responses = []


async def save_raw_response(response: httpx.Response) -> None:
    """httpx hook: keep the exact JSON the server sent for each POST."""
    if response.request.method == "POST":
        await response.aread()
        raw_responses.append(response.json())


def shorten_raw(value):
    """Cut long base64 'raw' fields (the PDF) so the printout stays readable."""
    if isinstance(value, dict):
        return {
            k: (f"{v[:40]}... ({len(v)} chars)" if k == "raw" and isinstance(v, str) and len(v) > 60 else shorten_raw(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [shorten_raw(v) for v in value]
    return value


def print_raw_step(step: str) -> None:
    print(f"\n----- Raw JSON-RPC response ({step}) -----")
    print(json.dumps(shorten_raw(raw_responses[-1]), indent=2, ensure_ascii=False))
    print("-----")


def ask_yes_no(question: str) -> bool:
    while True:
        answer = input(f"{question} [y/n] ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


async def send(client, message: Message):
    """Send one message and return the task from the response."""
    start = time.perf_counter()
    async for response in client.send_message(SendMessageRequest(message=message)):
        task = response.task
    print(f"\nTask status: {TaskState.Name(task.status.state)}   ({time.perf_counter() - start:.1f} s)")
    return task


def print_report(report: dict) -> None:
    print(f"\n===== Match report: {report['job_title']} ({report['company']}) =====")
    # Numbers arrive as floats (protobuf), so :g prints 66 instead of 66.0.
    print(f"Score: {report['score_percent']:g}%  ({report['points']:g} of {report['max_points']:g} points)\n")
    print("Matched (with proof from the CV):")
    for i in report["matched"]:
        print(f"  + [{i['kind']}] {i['item']}\n      \"{i['quote']}\"")
    print("Confirmed by you:")
    for i in report["confirmed_by_user"]:
        print(f"  + [{i['kind']}] {i['item']}")
    print("Missing:")
    for i in report["missing"]:
        print(f"  - [{i['kind']}] {i['item']}")
    print("Unclear (counted as not matched):")
    for i in report["unclear"]:
        print(f"  ? [{i['kind']}] {i['item']}" + (f"   ({i['note']})" if i["note"] else ""))
    print(f"\nSummary: {report['summary']}")


async def main(requirements_file: Path, cv_file: Path) -> None:
    result = json.loads(requirements_file.read_text(encoding="utf-8"))
    # Accept a run_all_samples result file, or a plain requirements JSON.
    requirements = result.get("requirements", result)
    if not requirements:
        sys.exit(f"{requirements_file} has no requirements (did the Job Analyst fail?)")

    async with httpx.AsyncClient(timeout=400, event_hooks={"response": [save_raw_response]}) as http:
        # AGENT CARD: fetch it, then build a client from it.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        print(f"Agent card: {card.name} {card.version} - input modes {list(card.default_input_modes)}")
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        # MESSAGE with two PARTS: requirements as a DATA part, the CV as a FILE part (raw bytes).
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[
                new_data_part(requirements, media_type="application/json"),
                new_raw_part(cv_file.read_bytes(), media_type="application/pdf", filename=cv_file.name),
            ],
        )
        print(f"Sending {requirements_file.name} + {cv_file.name} ... (the model may take a minute)")
        task = await send(client, message)
        print_raw_step("first message")

        # INPUT-REQUIRED: the agent paused and asks questions in the status message.
        while task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            questions = next(d["questions"] for d in get_data_parts(task.status.message.parts) if "questions" in d)
            print("\nThe CV Matcher has questions:")
            answers = {q["id"]: ask_yes_no(q["question"]) for q in questions}

            # Same TASK id and context id -> the agent continues the paused task.
            reply = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                task_id=task.id,
                context_id=task.context_id,
                parts=[new_data_part({"answers": answers})],
            )
            task = await send(client, reply)
            print_raw_step("answers")

        if task.status.state == TaskState.TASK_STATE_COMPLETED:
            # ARTIFACT: one DATA part with the report.
            print_report(get_data_parts(task.artifacts[0].parts)[0])
        elif task.status.HasField("message"):
            print(f"Status message: {get_message_text(task.status.message)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python scripts/test_cv_matcher.py <job_analyst_result.json> <cv.pdf>")
    asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2])))
