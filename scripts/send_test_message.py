"""Send one test message to the Job Analyst and print what comes back.

Run with:  python scripts/send_test_message.py   (the agent must be running)
"""

import asyncio
import json
import uuid

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_artifact_text
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

AGENT_URL = "http://localhost:9001"

SAMPLE_JOB_AD = (
    "Junior Python Developer. We need 1+ years of Python, basic SQL, "
    "Git, and good English. Docker is a plus."
)

raw_responses = []


async def save_raw_response(response: httpx.Response) -> None:
    """httpx hook: keep the exact JSON the server sent for each POST."""
    if response.request.method == "POST":
        await response.aread()
        raw_responses.append(response.json())


async def main() -> None:
    async with httpx.AsyncClient(event_hooks={"response": [save_raw_response]}) as http:
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
            parts=[Part(text=SAMPLE_JOB_AD)],
        )

        async for response in client.send_message(SendMessageRequest(message=message)):
            # TASK: the server answered with a task object.
            task = response.task
            # STATUS: the task's current state, e.g. TASK_STATE_COMPLETED.
            print(f"Task id:     {task.id}")
            print(f"Task status: {TaskState.Name(task.status.state)}")
            # ARTIFACT: the result the agent produced.
            for artifact in task.artifacts:
                print(f"Artifact '{artifact.name}': {get_artifact_text(artifact)}")

    print("\nRaw JSON-RPC response from the server (exactly what came over HTTP):")
    for raw in raw_responses:
        print(json.dumps(raw, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
