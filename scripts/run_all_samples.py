"""Send job ads to the Job Analyst and save each result as JSON (the batch runner for model comparisons).

Run with:  python -m scripts.run_all_samples                       every ad in samples/*.txt
           python -m scripts.run_all_samples samples/demo/job_ad_nurse.txt ...   only these ads
           python -m scripts.run_all_samples --out results/compare       another results folder
(the Job Analyst must be running on port 9001)

Results:   <out>/<model>/<ad name>.json, plus a copy of the prompt used. The model folder is named after
the model the agent reports in its result metadata: the model is the agent's choice, not this script's.
The whole batch uses one A2A context id, so the budget guard's per-run limit covers the whole batch.
"""

import argparse
import asyncio
import json
import shutil
import time
import uuid
from pathlib import Path

import httpx
from google.protobuf.json_format import MessageToDict

from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
from a2a.helpers import get_data_parts, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest, TaskState

from agents.model_client import PROJECT_ROOT, RESULTS_DIR, USAGE_KEY, model_folder_name

AGENT_URL = "http://localhost:9001"
SAMPLES_DIR = PROJECT_ROOT / "samples"
PROMPT_FILE = PROJECT_ROOT / "prompts" / "job_analyst.md"


def reported_usage(task) -> dict:
    """The agent's usage report (model, tokens, cost) from the artifact or the failure message."""
    sources = [a.metadata for a in task.artifacts]
    if task.status.HasField("message"):
        sources.append(task.status.message.metadata)
    for metadata in sources:
        data = MessageToDict(metadata)
        if USAGE_KEY in data:
            return data[USAGE_KEY]
    return {}


async def main(ad_files: list[Path], out_root: Path) -> None:
    context_id = str(uuid.uuid4())  # one context for the whole batch
    print(f"Ads: {len(ad_files)}   Results under: {out_root}   (context {context_id})\n")

    total_cost = 0.0
    async with httpx.AsyncClient(timeout=300) as http:
        # AGENT CARD: read it once, then build one client for all ads.
        card = await A2ACardResolver(http, AGENT_URL).get_agent_card()
        client = ClientFactory(ClientConfig(httpx_client=http, streaming=False)).create(card)

        for ad_file in ad_files:
            # MESSAGE from the user, with one text PART holding the job ad.
            message = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                context_id=context_id,
                parts=[Part(text=ad_file.read_text(encoding="utf-8"))],
            )
            start = time.perf_counter()
            async for response in client.send_message(SendMessageRequest(message=message)):
                task = response.task  # TASK returned by the agent
            seconds = round(time.perf_counter() - start, 1)

            # STATUS, ARTIFACT (one DATA part) and the agent's usage report.
            status = TaskState.Name(task.status.state)
            data = [d for a in task.artifacts for d in get_data_parts(a.parts)]
            usage = reported_usage(task)
            model = usage.get("model", "unknown-model")
            total_cost += float(usage.get("cost_usd", 0.0))
            result = {
                "ad_file": ad_file.name,
                "model": model,
                "agent_version": card.version,
                "seconds": seconds,
                "status": status,
                "error": get_message_text(task.status.message) if task.status.HasField("message") else None,
                "model_usage": usage,
                "requirements": data[0] if data else None,
            }
            out_dir = out_root / model_folder_name(model)
            out_dir.mkdir(parents=True, exist_ok=True)
            # Keep a copy of the prompt next to the results it produced.
            shutil.copy(PROMPT_FILE, out_dir / PROMPT_FILE.name)
            out_file = out_dir / f"{ad_file.stem}.json"
            out_file.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"{ad_file.name:<26} {model:<18} {status:<22} {seconds:>6.1f} s")

    print(f"\nModel cost of this batch: ${total_cost:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send job ads to the Job Analyst and save the results.")
    parser.add_argument("ads", nargs="*", type=Path, help="job ad files (default: samples/*.txt)")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR, help="results folder (default: results/)")
    args = parser.parse_args()
    asyncio.run(main(args.ads or sorted(SAMPLES_DIR.glob("*.txt")), args.out))
