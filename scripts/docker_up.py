"""Start (or stop) the four agents in Docker, optionally with the trace viewers Jaeger and Phoenix.

Run with:  python scripts/docker_up.py                       local models (the default), no tracing
           python scripts/docker_up.py --preset haiku        Claude Haiku (the key goes in as an environment variable)
           python scripts/docker_up.py --tracing             also start Jaeger and Phoenix; the agents send traces
           python scripts/docker_up.py --tracing --content   also record prompts, CV text and letters (demo CVs only)
           python scripts/docker_up.py --down                stop and remove the containers

Then run the orchestrator in your terminal, as without Docker (it asks you questions). With --tracing,
give it TRACING=on too (and TRACE_CONTENT=on for --content), e.g.:
           TRACING=on python -m orchestrator samples/demo/job_ad_demo.txt samples/demo/cv_jane_doe.pdf \\
               --answers samples/demo/answers_jane_doe.json

Before starting, it checks that the ports are free. The trace viewers use the same ports as the
labour-law project's viewers, so those must be stopped first.
Uses only the Python standard library (plus docker compose).
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from start_agents import AGENTS, PRESETS, is_ready  # same folder: the presets are the same as without Docker

PROJECT_ROOT = Path(__file__).resolve().parent.parent
READY_TIMEOUT_SECONDS = 120  # the first start builds the image
VIEWER_PORTS = {16686: "Jaeger's page", 4318: "Jaeger's trace intake", 6006: "Phoenix"}
VIEWER_SERVICES = ("jaeger", "phoenix")
STOP_LABOUR_LAW = "docker compose --profile observability stop jaeger phoenix   (in the labour-law project)"


def busy_ports(ports) -> list[int]:
    """The ports something on this machine already listens on."""
    busy = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.3)
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                busy.append(port)
    return busy


def port_messages(tracing: bool) -> list[str]:
    """One clear line per busy port, saying what probably uses it and what to do."""
    messages = []
    for port in busy_ports(int(url.rsplit(":", 1)[1]) for *_, url, _ in AGENTS):
        messages.append(f"Port {port} is busy: agents are probably running already "
                        f"(Ctrl+C in start_agents.py's terminal, or: python scripts/docker_up.py --down).")
    if tracing:
        for port in busy_ports(VIEWER_PORTS):
            messages.append(f"Port {port} ({VIEWER_PORTS[port]}) is busy: probably the labour-law project's viewers. "
                            f"Stop them first: {STOP_LABOUR_LAW}. To see what uses it: lsof -nP -iTCP:{port} -sTCP:LISTEN")
    return messages


def compose(*args: str, env: dict | None = None, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "compose", *args], cwd=PROJECT_ROOT, env=env,
                          text=True, capture_output=capture, check=False)


def stopped_agents() -> list[str]:
    """Agent containers that exited (e.g. a failed key check)."""
    output = compose("ps", "--all", "--format", "json", capture=True).stdout.strip()
    # Newer compose prints one JSON object per line, older versions one JSON list.
    containers = json.loads(output) if output.startswith("[") else [json.loads(x) for x in output.splitlines() if x.strip()]
    return [c["Service"] for c in containers if c.get("State") == "exited" and c["Service"] not in VIEWER_SERVICES]


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the agents in Docker (optionally with the trace viewers).")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="local",
                        help="local (Ollama on the Mac, the default) or haiku (Claude, cloud, paid)")
    parser.add_argument("--tracing", action="store_true", help="start Jaeger and Phoenix; agents send traces")
    parser.add_argument("--content", action="store_true",
                        help="record prompts, CV text and letters in traces (only with the fictional demo CVs)")
    parser.add_argument("--down", action="store_true", help="stop and remove the containers")
    args = parser.parse_args()

    if args.down:
        return compose("--profile", "tracing", "down").returncode
    if args.content and not args.tracing:
        sys.exit("--content only makes sense with --tracing.")

    problems = port_messages(args.tracing)
    if problems:
        print("\n".join(problems))
        return 1

    models = PRESETS[args.preset]
    env = {**os.environ, **models,
           "TRACING": "on" if args.tracing else "off",
           "TRACE_CONTENT": "on" if args.content else "off"}
    if not any(m.startswith("claude-") for m in models.values()):
        env["ANTHROPIC_API_KEY"] = ""  # local models: the containers get no key at all

    print(f"Preset: {args.preset} ({', '.join(f'{name}: {models[setting]}' for name, _, _, setting in AGENTS)})")
    if args.preset != "local":
        print("With Claude, the job ad, the CV text and the letter are sent to Anthropic.")
    profile = ["--profile", "tracing"] if args.tracing else []
    if compose(*profile, "up", "-d", "--build", env=env).returncode != 0:
        return 1

    # READY: wait for every agent card, like start_agents.py; stop early if an agent exited.
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    waiting = [(name, url) for name, _, url, _ in AGENTS]
    while waiting and time.monotonic() < deadline:
        exited = stopped_agents()
        if exited:
            print(f"Stopped during startup: {', '.join(exited)}. Its message:")
            compose("logs", "--tail", "5", *exited)
            return 1
        waiting = [(name, url) for name, url in waiting if not is_ready(url)]
        time.sleep(0.5)
    if waiting:
        print(f"Not ready after {READY_TIMEOUT_SECONDS} s: {', '.join(n for n, _ in waiting)}. See: docker compose logs")
        return 1

    print("\nAll agents are ready (in Docker). Run the pipeline in this terminal:")
    trace_env = "TRACING=on " + ("TRACE_CONTENT=on " if args.content else "") if args.tracing else ""
    print(f"  {trace_env}python -m orchestrator samples/demo/job_ad_demo.txt samples/demo/cv_jane_doe.pdf "
          f"--answers samples/demo/answers_jane_doe.json")
    if args.tracing:
        print("Trace viewers:  Jaeger http://localhost:16686   Phoenix http://localhost:6006")
    print("Stop everything with:  python scripts/docker_up.py --down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
