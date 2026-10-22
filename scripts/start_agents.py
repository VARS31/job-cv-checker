"""Start all agents in one terminal; Ctrl+C stops them all.

Run with:  python scripts/start_agents.py
Uses only the Python standard library (subprocess, threading, urllib).
"""

import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS = [
    ("job_analyst", "agents.job_analyst", "http://localhost:9001"),
    ("cv_matcher", "agents.cv_matcher", "http://localhost:9002"),
    ("cover_letter", "agents.cover_letter_writer", "http://localhost:9003"),
    ("reviewer", "agents.application_reviewer", "http://localhost:9004"),
]
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
    # Ctrl+C (SIGINT) and a plain kill (SIGTERM) both stop all agents cleanly,
    # also when this script runs in the background.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, stop_on_sigterm)
    sys.stdout.reconfigure(line_buffering=True)  # show our lines at once, also when redirected
    processes = []
    for name, module, url in AGENTS:
        if is_ready(url):
            sys.exit(f"Something is already running at {url}. Stop it first (Ctrl+C in its terminal).")
        process = subprocess.Popen(
            [sys.executable, "-u", "-m", module],  # -u: print output right away
            cwd=PROJECT_ROOT,
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
