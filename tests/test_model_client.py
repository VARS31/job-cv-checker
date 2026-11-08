"""The model client's routing, schema adapter, limit check, usage report and startup check (no network)."""

import importlib

import anthropic
import httpx2
import pytest

from agents import model_client
from agents.model_client import (
    ModelError,
    Usage,
    check_array_limits,
    claude_schema,
    is_claude_model,
    startup_check,
)

FAKE_KEY = "sk-ant-test-FAKE-KEY-0000"

AGENT_SCHEMAS = {
    "job_analyst": ("agents.job_analyst.schema", "REQUIREMENTS_SCHEMA"),
    "cv_matcher": ("agents.cv_matcher.schema", "CHECK_SCHEMA"),
    "cover_letter_writer": ("agents.cover_letter_writer.schema", "LETTER_SCHEMA"),
    "application_reviewer": ("agents.application_reviewer.schema", "REVIEW_SCHEMA"),
}


def schema(agent: str) -> dict:
    module, name = AGENT_SCHEMAS[agent]
    return getattr(importlib.import_module(module), name)


def walk(node):
    """Every dict inside a schema."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def test_claude_names_mean_claude_everything_else_ollama():
    assert is_claude_model("claude-haiku-5-5")
    assert is_claude_model(" Claude-Haiku-5-5 ")
    assert not is_claude_model("ministral-3:8b")
    assert not is_claude_model("granite4.1:8b")


@pytest.mark.parametrize("agent", AGENT_SCHEMAS)
def test_every_agent_schema_converts_for_claude(agent):
    converted = claude_schema(schema(agent))
    for node in walk(converted):
        assert "maxItems" not in node
        assert node.get("minItems", 0) in (0, 1)
        assert not isinstance(node.get("type"), list)
        if node.get("type") == "object":
            assert node["additionalProperties"] is False


def test_conversion_keeps_the_original_schema_unchanged():
    original = schema("job_analyst")
    before = repr(original)
    claude_schema(original)
    assert repr(original) == before  # Ollama still gets exactly the old schema


def test_number_or_null_becomes_any_of():
    years = claude_schema(schema("job_analyst"))["properties"]["min_years_experience"]
    assert years["anyOf"] == [{"type": "number"}, {"type": "null"}]


def test_array_limits_move_into_the_description():
    converted = claude_schema(schema("application_reviewer"))
    assert "minItems: 3" in converted["properties"]["top_weaknesses"]["description"]
    assert "maxItems: 5" in converted["properties"]["interview_questions"]["description"]


def test_extra_items_are_cut_with_a_note():
    data = {"responsibilities": [f"r{n}" for n in range(8)]}
    data, notes = check_array_limits(data, schema("job_analyst"))
    assert data["responsibilities"] == [f"r{n}" for n in range(6)]
    assert notes == ["answer.responsibilities: 8 items, cut to the schema's maximum of 6"]


def test_too_few_items_is_an_error():
    review = {"top_weaknesses": [{"weakness": "w", "requirement": "r"}], "interview_questions": ["q"] * 3}
    with pytest.raises(ModelError, match="at least 3"):
        check_array_limits(review, schema("application_reviewer"))


def test_usage_adds_up_and_survives_protobuf_floats():
    usage = Usage("claude-haiku-5-5")
    usage.add(1000, 200, 0.0002, 1.5)
    usage.add(500, 100, 0.0001, 0.5)
    meta = usage.as_metadata()
    assert meta["provider"] == "anthropic"
    assert (meta["calls"], meta["input_tokens"], meta["output_tokens"]) == (2, 1500, 300)
    as_floats = {k: float(v) if isinstance(v, int) else v for k, v in meta.items()}
    back = Usage.from_metadata(as_floats)
    assert back.calls == 2 and isinstance(back.input_tokens, int)
    assert Usage("ministral-3:8b").provider == "ollama"


# --- Startup check -----------------------------------------------------------------------------------

def test_local_model_needs_ollama_url(isolated_settings):
    with pytest.raises(SystemExit, match="OLLAMA_URL"):
        startup_check("Job Analyst", "ministral-3:8b")
    isolated_settings.write_text("OLLAMA_URL=http://localhost:11434\n")
    startup_check("Job Analyst", "ministral-3:8b")  # no exit


def test_claude_model_without_key_does_not_start():
    with pytest.raises(SystemExit) as stop:
        startup_check("CV Matcher", "claude-haiku-5-5")
    assert "ANTHROPIC_API_KEY is not set" in str(stop.value)
    assert "Not starting" in str(stop.value)


def test_claude_model_without_a_price_does_not_start(isolated_settings):
    isolated_settings.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n")
    with pytest.raises(SystemExit, match="no price"):
        startup_check("CV Matcher", "claude-unknown-9")


class RejectingSDK:
    """Stands in for anthropic.Anthropic: the API answers 401 to the free model lookup."""

    def __init__(self, **kwargs):
        self.models = self

    def retrieve(self, model):
        request = httpx2.Request("GET", f"https://api.anthropic.com/v1/models/{model}")
        response = httpx2.Response(401, request=request)
        raise anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)


def test_rejected_key_stops_the_agent_and_never_shows_the_key(isolated_settings, monkeypatch, capsys):
    isolated_settings.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n")
    monkeypatch.setattr(anthropic, "Anthropic", RejectingSDK)
    with pytest.raises(SystemExit) as stop:
        startup_check("Application Reviewer", "claude-haiku-5-5")
    message = str(stop.value)
    assert "rejected ANTHROPIC_API_KEY" in message
    printed = capsys.readouterr()
    assert FAKE_KEY not in message + printed.out + printed.err
    assert stop.value.__cause__ is None and stop.value.__suppress_context__  # no traceback with request details


def test_working_key_starts_and_says_where_text_goes(isolated_settings, monkeypatch, capsys):
    isolated_settings.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n")

    class AcceptingSDK(RejectingSDK):
        def retrieve(self, model):
            return {"id": model}

    monkeypatch.setattr(anthropic, "Anthropic", AcceptingSDK)
    startup_check("Job Analyst", "claude-haiku-5-5")
    out = capsys.readouterr().out
    assert "sent to Anthropic" in out
    assert FAKE_KEY not in out
    assert model_client._agent_name == "Job Analyst"
