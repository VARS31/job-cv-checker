"""Tracing (agents/tracing.py): off by default, gen_ai spans, the content switch, the key, the trace context
across HTTP, and one warning when the viewers are down. No network: spans go to an in-memory exporter."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from agents import model_client, tracing
from agents.cv_matcher.schema import apply_model_checks, build_check_input, build_checklist, check_summary

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "sk-ant-test-FAKE-KEY-0000"


@pytest.fixture
def spans(monkeypatch):
    """Tracing on, with spans kept in memory (the global provider is never touched)."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "tracer", lambda: provider.get_tracer("test"))
    monkeypatch.setitem(tracing._state, "on", True)
    monkeypatch.setitem(tracing._state, "content", False)
    return exporter


@pytest.fixture
def fake_ollama(monkeypatch, isolated_settings):
    """Ollama answered by a stand-in, so ask_model runs for real without a model."""
    isolated_settings.write_text("OLLAMA_URL=http://ollama.test\n")
    real_client = httpx.AsyncClient

    def answer(request):
        return httpx.Response(200, json={
            "model": "ministral-3:8b", "message": {"content": '{"ok": true}'},
            "prompt_eval_count": 120, "eval_count": 7, "done_reason": "stop",
        })

    monkeypatch.setattr(model_client.httpx, "AsyncClient",
                        lambda **kwargs: real_client(transport=httpx.MockTransport(answer), **kwargs))


def ask(prompt="CV text of Jane Doe", model="ministral-3:8b"):
    usage = model_client.Usage(model)
    text = asyncio.run(model_client.ask_model(prompt, model, system="the instructions", usage=usage))
    return text, usage


def all_attribute_values(exporter) -> str:
    return " ".join(str(value) for s in exporter.get_finished_spans() for value in s.attributes.values())


# --- Off by default -------------------------------------------------------------------------------------

def test_tracing_is_off_by_default():
    assert tracing.setup("test") is False
    assert not tracing.enabled()
    with tracing.span("anything", {"a": 1}) as current:
        assert not current.is_recording()


def test_off_and_on_give_the_same_result(fake_ollama, monkeypatch):
    off_text, off_usage = ask()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(tracing, "tracer", lambda: provider.get_tracer("test"))
    monkeypatch.setitem(tracing._state, "on", True)
    on_text, on_usage = ask()
    assert off_text == on_text == '{"ok": true}'
    assert (off_usage.input_tokens, off_usage.output_tokens) == (on_usage.input_tokens, on_usage.output_tokens)
    assert len(exporter.get_finished_spans()) == 1


# --- Model-call spans ---------------------------------------------------------------------------------

def test_model_call_span_has_standard_gen_ai_attributes(fake_ollama, spans):
    ask()
    (span,) = spans.get_finished_spans()
    a = span.attributes
    assert span.name == "chat ministral-3:8b"
    assert a["gen_ai.operation.name"] == "chat"
    assert a["gen_ai.provider.name"] == "ollama"
    assert a["gen_ai.request.model"] == "ministral-3:8b"
    assert (a["gen_ai.usage.input_tokens"], a["gen_ai.usage.output_tokens"]) == (120, 7)
    assert a["gen_ai.response.finish_reasons"] == ("stop",)
    assert a["llm.cost.total"] == 0.0
    assert a["openinference.span.kind"] == "LLM"


def test_no_content_without_the_switch_and_the_runs_permission(fake_ollama, spans, monkeypatch):
    ask()
    monkeypatch.setitem(tracing._state, "content", True)
    ask()  # switch on, but the run didn't allow it
    with tracing.allow_content():
        ask()  # switch on and allowed
    first, second, third = spans.get_finished_spans()
    for span in (first, second):
        assert "input.value" not in span.attributes and "output.value" not in span.attributes
    assert third.attributes["input.value"] == "CV text of Jane Doe"
    assert third.attributes["output.value"] == '{"ok": true}'


def test_claude_call_span_has_cost_and_never_the_key(spans, monkeypatch, isolated_settings):
    isolated_settings.write_text(f"ANTHROPIC_API_KEY={FAKE_KEY}\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setitem(tracing._state, "content", True)
    response = SimpleNamespace(
        stop_reason="end_turn", model="claude-haiku-5-5",
        content=[SimpleNamespace(type="text", text="the letter")],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_creation_input_tokens=0,
                              cache_read_input_tokens=0, output_tokens_details=SimpleNamespace(thinking_tokens=150)),
    )

    class FakeMessages:
        async def create(self, **request):
            return response

    monkeypatch.setattr(model_client, "_claude", lambda timeout: SimpleNamespace(messages=FakeMessages()))
    with tracing.allow_content():
        text, usage = ask(model="claude-haiku-5-5")
    assert text == "the letter"
    (span,) = spans.get_finished_spans()
    assert span.attributes["gen_ai.provider.name"] == "anthropic"
    assert span.attributes["gen_ai.usage.reasoning.output_tokens"] == 150
    assert span.attributes["llm.cost.total"] == pytest.approx(usage.cost_usd)
    assert FAKE_KEY not in all_attribute_values(spans)


# --- One trace across processes: the context travels in the HTTP headers --------------------------------

def test_trace_context_and_content_permission_cross_http(spans, monkeypatch):
    monkeypatch.setitem(tracing._state, "content", True)
    seen = {}

    async def endpoint(request):
        context = tracing.current_span().get_span_context()  # the caller's span, read from the headers
        seen.update(trace_id=context.trace_id, span_id=context.span_id, content=tracing.record_content())
        return JSONResponse({})

    app = tracing.TraceContextMiddleware(Starlette(routes=[Route("/", endpoint, methods=["POST"])]))

    async def call():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, event_hooks={"request": [tracing.inject_headers]}) as http:
            with tracing.allow_content(), tracing.span("client") as client_span:
                await http.post("http://agent.test/")
                return client_span.get_span_context()

    client = asyncio.run(call())
    assert (seen["trace_id"], seen["span_id"]) == (client.trace_id, client.span_id)
    assert seen["content"] is True  # the run's permission arrived as baggage


def test_middleware_passes_requests_through_when_off():
    async def endpoint(request):
        return JSONResponse({"traceparent": request.headers.get("traceparent")})

    app = tracing.TraceContextMiddleware(Starlette(routes=[Route("/", endpoint)]))

    async def call():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app)) as http:
            return (await http.get("http://agent.test/")).json()

    assert asyncio.run(call()) == {"traceparent": None}


# --- Viewers down: one warning, the run goes on -----------------------------------------------------------

class FailingExporter:
    def export(self, spans):
        raise ConnectionError("viewer down")

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


def test_viewer_exporter_warns_once(monkeypatch, capsys):
    monkeypatch.setitem(tracing._state, "warned", False)
    exporter = tracing.ViewerExporter("Jaeger", FailingExporter())
    assert exporter.export([]) is SpanExportResult.FAILURE
    assert exporter.export([]) is SpanExportResult.FAILURE
    assert capsys.readouterr().err.count("[tracing]") == 1
    assert exporter.failed


def test_viewers_down_cost_one_warning_and_no_failure():
    """In a fresh process (setup() sets the global provider): tracing on, nothing listening."""
    code = ("from agents import tracing\n"
            "assert tracing.setup('test')\n"
            "with tracing.span('run') as s: pass\n"
            "tracing.shutdown()\n"
            "print('run finished')\n")
    env = {**os.environ, "TRACING": "on", "JAEGER_OTLP_URL": "http://127.0.0.1:9/v1/traces",
           "PHOENIX_OTLP_URL": "http://127.0.0.1:9/v1/traces", "PYTHONPATH": str(ROOT)}
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "run finished" in result.stdout
    assert result.stderr.count("[tracing]") == 1
    assert "not running" in result.stderr


# --- Grounding-check counts and today's date ----------------------------------------------------------------

def test_quote_check_summary_counts_what_changed():
    requirements = {"hard_skills_required": ["Python", "Go"], "other_requirements": ["Occasional travel"],
                    "hard_skills_preferred": ["Docker"]}
    checklist = build_checklist(requirements)
    checks = [{"id": "r1", "status": "found", "quote": "Python daily"},
              {"id": "r2", "status": "found", "quote": "invented"},
              {"id": "r3", "status": "missing", "quote": ""}]
    summary = check_summary(apply_model_checks(checklist, checks, "I write Python daily."))
    assert summary["cvchecker.check.items"] == 4
    assert summary["cvchecker.check.found"] == 1
    assert summary["cvchecker.check.quote_not_in_cv"] == 1
    assert summary["cvchecker.check.cannot_show_asked"] == 1
    assert summary["cvchecker.check.no_answer"] == 1


def test_cv_matcher_input_starts_with_todays_date():
    text = build_check_input([{"id": "r1", "kind": "required", "text": "Python"}], "CV", "2026-11-09")
    assert text.startswith("TODAY'S DATE: 2026-11-09\n")
    assert "r1 [required] Python" in text


def test_sdk_internal_spans_are_left_out():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(tracing.SkipSdkInternals(SimpleSpanProcessor(exporter)))
    tracer = provider.get_tracer("test")
    for name in ("a2a.server.events.event_queue_v2.EventQueueSource._dispatch",
                 "a2a.server.tasks.task_manager.TaskManager.save",
                 "a2a.client.transports.jsonrpc.JsonRpcTransport.send_message",
                 "a2a.server.routes.jsonrpc_dispatcher.JsonRpcDispatcher.handle_requests",
                 "chat claude-haiku-5-5"):
        with tracer.start_as_current_span(name):
            pass
    assert [s.name for s in exporter.get_finished_spans()] == [
        "a2a.client.transports.jsonrpc.JsonRpcTransport.send_message",
        "a2a.server.routes.jsonrpc_dispatcher.JsonRpcDispatcher.handle_requests",
        "chat claude-haiku-5-5",
    ]
