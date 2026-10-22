"""Send every job ad in samples/ to the Job Analyst and save each result as JSON.

Run with:  python -m scripts.run_all_samples   (the agent must be running)
Results:   results/<model>/<ad name>.json, plus a copy of the prompt used.
"""

import asyncio
import json
import shutil
import time
import uuid

import httpx

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

from agents.model_client import PROJECT_ROOT, RESULTS_DIR, model_folder_name, read_setting

AGENT_URL = "http://localhost:9001"
SAMPLES_DIR = PROJECT_ROOT / "samples"
PROMPT_FILE = PROJECT_ROOT / "prompts" / "job_analyst.md"


async def main() -> None:
    # Same setting the agent reads. Restart the agent after changing it in .env.
    model = read_setting("JOB_ANALYST_MODEL")
    out_dir = RESULTS_DIR / model_folder_name(model)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Keep a copy of the prompt next to the results it produced.
    shutil.copy(PROMPT_FILE, out_dir / PROMPT_FILE.name)

    ad_files = sorted(SAMPLES_DIR.glob("*.txt"))
    print(f"Model: {model}   Ads: {len(ad_files)}   Saving to: {out_dir}\n")

    async with httpx.AsyncClient(timeout=300) as http:
        # AGENT CARD: read it once, then build one client for all ads.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        for ad_file in ad_files:
            # MESSAGE from the user, with one text PART holding the job ad.
            message = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                parts=[Part(text=ad_file.read_text(encoding="utf-8"))],
            )
            start = time.perf_counter()
            async for response in client.send_message(SendMessageRequest(message=message)):
                task = response.task  # TASK returned by the agent
            seconds = round(time.perf_counter() - start, 1)

            # STATUS and ARTIFACT (one DATA part) of the task.
            status = TaskState.Name(task.status.state)
            data = [d for a in task.artifacts for d in get_data_parts(a.parts)]
            result = {
                "ad_file": ad_file.name,
                "model": model,
                "agent_version": card.version,
                "seconds": seconds,
                "status": status,
                "error": get_message_text(task.status.message) if task.status.HasField("message") else None,
                "requirements": data[0] if data else None,
            }
            out_file = out_dir / f"{ad_file.stem}.json"
            out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{ad_file.name:<16} {status:<22} {seconds:>6.1f} s")


if __name__ == "__main__":
    asyncio.run(main())
