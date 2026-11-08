"""Start all agents in one terminal; Ctrl+C stops them all.

Run with:  python scripts/start_agents.py                  local models (the default)
           python scripts/start_agents.py --preset haiku   Claude Haiku for all four (cloud, paid)

A preset sets each agent's model setting (e.g. JOB_ANALYST_MODEL) for the agents started here; it
overrides the *_MODEL lines in .env. An agent started on its own (python -m agents.<name>) reads .env.
Uses only the Python standard library (argparse, subprocess, threading, urllib).
"""

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# (short name, module, URL, the setting that holds its model)
AGENTS = [
    ("job_analyst", "agents.job_analyst", "http://localhost:9001", "JOB_ANALYST_MODEL"),
    ("cv_matcher", "agents.cv_matcher", "http://localhost:9002", "CV_MATCHER_MODEL"),
    ("cover_letter", "agents.cover_letter_writer", "http://localhost:9003", "COVER_LETTER_MODEL"),
    ("reviewer", "agents.application_reviewer", "http://localhost:9004", "REVIEWER_MODEL"),
]
# Local by default, cloud optional. The local models were chosen by measurement (docs/model-comparison-job-analyst.md);
# the Reviewer uses a different local model on purpose (docs/decisions.md, decision 4).
PRESETS = {
    "local": {
        "JOB_ANALYST_MODEL": "ministral-3:8b",
        "CV_MATCHER_MODEL": "ministral-3:8b",
        "COVER_LETTER_MODEL": "ministral-3:8b",
        "REVIEWER_MODEL": "granite4.1:8b",
    },
    "haiku": {
        "JOB_ANALYST_MODEL": "claude-haiku-5-5",
        "CV_MATCHER_MODEL": "claude-haiku-5-5",
        "COVER_LETTER_MODEL": "claude-haiku-5-5",
        "REVIEWER_MODEL": "claude-haiku-5-5",
    },
}
READY_TIMEOUT_SECONDS = 30


def forward_output(name: str, process: subprocess.Popen) -> None:
    """Print each line of an agent's output with its name in front."""
    for line in process.stdout:
        print(f"[{name}] {line}", end="", flush=True)


def is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/.well-known/agent-card.json", timeout=1) as response:
            return response.status == 200
    except OSError:
        return False


def stop_on_sigterm(signum, frame) -> None:
    """Treat a plain kill like Ctrl+C, so the agents are stopped too."""
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description="Start all four agents; Ctrl+C stops them.")
    parser.add_argument(
        "--preset", choices=sorted(PRESETS), default="local",
        help="which models the agents use: local (Ollama, the default) or haiku (Claude, cloud, paid)",
    )
    preset = parser.parse_args().preset
    models = PRESETS[preset]
    print(f"Preset: {preset}")
    for name, _, _, setting in AGENTS:
        print(f"  {name}: {models[setting]}")
    if any(m.startswith("claude-") for m in models.values()):
        print("  With Claude, the job ad, the CV text and the letter are sent to Anthropic.\n")

    # Ctrl+C (SIGINT) and a plain kill (SIGTERM) both stop all agents cleanly,
    # also when this script runs in the background.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    sys.stdout.reconfigure(line_buffering=True)  # show our lines at once, also when redirected
    processes = []
    for name, module, url, setting in AGENTS:
        if is_ready(url):
            sys.exit(f"Something is already running at {url}. Stop it first (Ctrl+C in its terminal).")
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", module],  # -u: print output right away
            cwd=PROJECT_ROOT,
            env={**os.environ, setting: models[setting]},  # the preset wins over .env
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=forward_output, args=(name, process), daemon=True).start()
        processes.append((name, url, process))

    try:
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        waiting = list(processes)
        while waiting and time.monotonic() < deadline:
            for entry in list(waiting):
                name, url, process = entry
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited during start-up (see its output above)")
                if is_ready(url):
                    waiting.remove(entry)
            time.sleep(0.3)
        if waiting:
            raise RuntimeError(f"not ready after {READY_TIMEOUT_SECONDS} s: {', '.join(n for n, _, _ in waiting)}")
        print("\nAll agents are ready. Run the pipeline in another terminal:")
        print("  python -m orchestrator samples/<job_ad>.txt samples/cvs/<cv>.pdf")
        print("Press Ctrl+C here to stop all agents.\n")

        while True:  # keep running; tell the user if an agent stops on its own
            for name, _, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} stopped unexpectedly (exit code {process.returncode})")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping all agents ...")
    except RuntimeError as error:
        print(f"\n{error}. Stopping all agents ...")
    finally:
        for _, _, process in processes:
            if process.poll() is None:
                process.terminate()
        for name, _, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            print(f"  {name} stopped")


if __name__ == "__main__":
    main()
