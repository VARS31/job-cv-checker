"""The Docker files keep secrets and personal files out, and publish nothing beyond this machine.
Plain text checks: no Docker needed to run them."""

import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))  # docker_up.py imports start_agents.py from its own folder

import docker_up  # noqa: E402


def test_dockerignore_denies_everything_but_the_code():
    lines = [line.strip() for line in (ROOT / ".dockerignore").read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    assert lines[0] == "*"
    allowed = [line[1:] for line in lines if line.startswith("!")]
    assert sorted(allowed) == ["agents/", "prompts/", "requirements.txt"]
    for secret in (".env", "samples/", "results/", "docs/learning-notes.md"):
        assert secret in lines


def test_dockerfile_copies_only_the_code_and_holds_no_key():
    text = (ROOT / "Dockerfile").read_text()
    copies = re.findall(r"^COPY (\S+)", text, re.MULTILINE)
    assert copies == ["requirements.txt", "agents/", "prompts/"]
    code = [line for line in text.splitlines() if not line.strip().startswith("#")]
    assert not any("ANTHROPIC" in line for line in code)  # the key is never set in the image


def test_compose_publishes_on_127_0_0_1_only():
    text = (ROOT / "docker-compose.yml").read_text()
    ports = re.findall(r'^\s+- "([^"]+:\d+:\d+)"', text, re.MULTILINE)
    assert len(ports) == 7  # four agents, Jaeger (2), Phoenix
    assert all(p.startswith("127.0.0.1:") for p in ports), ports


def test_compose_takes_the_key_from_the_environment_and_starts_viewers_only_for_tracing():
    text = (ROOT / "docker-compose.yml").read_text()
    assert "ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}" in text
    assert "env_file" not in text  # never hand the whole .env to the containers
    assert text.count("profiles: [tracing]") == 2
    for port in ("16686", "4318", "6006"):
        assert f'"127.0.0.1:{port}:{port}"' in text  # the same ports as the labour-law project


def test_busy_ports_are_found(monkeypatch):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert docker_up.busy_ports([port]) == [port]
    assert docker_up.busy_ports([port]) == []


def test_busy_viewer_port_message_names_the_labour_law_project(monkeypatch):
    monkeypatch.setattr(docker_up, "busy_ports", lambda ports: [p for p in ports if p == 6006])
    (message,) = docker_up.port_messages(tracing=True)
    assert "6006" in message and "labour-law" in message and "stop" in message.lower()
