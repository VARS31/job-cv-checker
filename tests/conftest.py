"""Shared test set-up: no test may read the real .env (it can hold the API key) or touch the real budget file."""

import pytest

from agents import model_client

SETTINGS = [
    "ANTHROPIC_API_KEY", "OLLAMA_URL", "BUDGET_PER_RUN_USD", "BUDGET_TOTAL_USD", "MODEL_DEBUG",
    "JOB_ANALYST_MODEL", "CV_MATCHER_MODEL", "COVER_LETTER_MODEL", "REVIEWER_MODEL",
]


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Every test gets an empty .env, no model settings in the environment, and its own budget file."""
    env_file = tmp_path / ".env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(model_client, "ENV_FILE", env_file)
    monkeypatch.setattr(model_client, "BUDGET_FILE", tmp_path / "cloud_spend.json")
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    return env_file
