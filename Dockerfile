# One image for all four agents: the same code, a different command per agent (see docker-compose.yml).
# Only what the agents need goes in: the Python packages, agents/ and prompts/. No .env, no CVs, no
# results (see .dockerignore). The API key is never in the image: compose passes it as an environment
# variable when a container starts, and only with the haiku preset.
FROM python:3.11.18-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Inside a container the agent must listen on all interfaces; compose publishes it on 127.0.0.1 only.
    AGENT_BIND_HOST=0.0.0.0

WORKDIR /app

# Packages first, so a code change doesn't reinstall them (Docker reuses this layer).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ agents/
COPY prompts/ prompts/

# The default command; compose picks the agent for each container.
CMD ["python", "-m", "agents.job_analyst"]
