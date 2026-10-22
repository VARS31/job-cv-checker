"""Send one job ad to the Job Analyst and print what comes back.

Run with:  python scripts/send_test_message.py samples/job_ad_1.txt   (the agent must be running)
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

AGENT_URL = "http://localhost:9001"

raw_responses = []


async def save_raw_response(response: httpx.Response) -> None:
    """httpx hook: keep the exact JSON the server sent for each POST."""
    if response.request.method == "POST":
        await response.aread()
        raw_responses.append(response.json())


async def main(job_ad: str) -> None:
    # The model can take a while, so allow up to 3 minutes per request.
    async with httpx.AsyncClient(
        timeout=180, event_hooks={"response": [save_raw_response]}
    ) as http:
        # AGENT CARD: fetch it from /.well-known/agent-card.json.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        print(f"Agent card: {card.name} - {card.description}")
        print(f"Skills: {[skill.name for skill in card.skills]}\n")

        # The client picks the transport (JSON-RPC) from the agent card.
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        # MESSAGE from the user, with one text PART holding the job ad.
        message = Message(
            role=Role.ROLE_USER,
            message_id=str(uuid.uuid4()),
            parts=[Part(text=job_ad)],
        )

        start = time.perf_counter()
        async for response in client.send_message(SendMessageRequest(message=message)):
            seconds = time.perf_counter() - start
            # TASK: the server answered with a task object.
            task = response.task
            # STATUS: the task's current state, e.g. TASK_STATE_COMPLETED or TASK_STATE_FAILED.
            print(f"Task id:     {task.id}")
            print(f"Task status: {TaskState.Name(task.status.state)}")
            print(f"Agent took:  {seconds:.1f} seconds")
            # On failure, the agent puts the error text in the status message.
            if task.status.HasField("message"):
                print(f"Status message: {get_message_text(task.status.message)}")
            # ARTIFACT: the result, here one DATA part with the requirements as JSON.
            for artifact in task.artifacts:
                for data in get_data_parts(artifact.parts):
                    print(f"\nArtifact '{artifact.name}':")
                    print(json.dumps(data, indent=2, ensure_ascii=False))

    print("\nRaw JSON-RPC response from the server (exactly what came over HTTP):")
    for raw in raw_responses:
        print(json.dumps(raw, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/send_test_message.py <job_ad_file.txt>")
    asyncio.run(main(Path(sys.argv[1]).read_text(encoding="utf-8")))
