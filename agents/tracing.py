"""Tracing with OpenTelemetry, shared by the orchestrator and all four agents. Off by default.

TRACING=on (in .env or the environment) turns it on. Each process then sends its spans over OTLP to
Jaeger and Phoenix, and one pipeline run becomes ONE trace across all five processes. Off, nothing is
set up: the OpenTelemetry API stays a no-op, and the program behaves exactly as without tracing.

What a trace holds:
- the orchestrator's root span for the run, and a span per pipeline step;
- inside each step, the A2A client span (orchestrator) and server span (agent). The A2A SDK makes those
  spans itself but doesn't pass the trace context between processes, so we do: inject_headers() puts it
  into the HTTP headers, TraceContextMiddleware reads it back in the agent;
- a span per model call, with OpenTelemetry's standard gen_ai.* names (model, tokens) and the cost;
- spans for the grounding checks, and the time the run waited for the user's answers.

Privacy:
- Content (prompts, CV text, letters, answers) is recorded only when TRACE_CONTENT=on AND the run allows
  it. The orchestrator allows it only for the fictional CVs in samples/demo/ and tells the agents through
  W3C baggage, so an agent never records a real CV's text, even if its own switch is on.
- The API key never goes into a span: nothing here reads it, and the Anthropic SDK's own tracing is off.
- A viewer that is down costs one warning, never the run.

Attribute names: gen_ai.* are OpenTelemetry's standard ones; openinference.*, llm.*, input.value and
output.value are what Phoenix reads; cvchecker.* are our own. They are plain strings: no extra package.
"""

import atexit
import logging
import os
import socket
import sys
from contextlib import contextmanager
from urllib.parse import urlsplit

from opentelemetry import baggage, propagate, trace
from opentelemetry import context as otel_context
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind, Status, StatusCode

PROJECT = "job-cv-checker"  # Phoenix groups every service's spans under this project
# Where each viewer takes traces (OTLP over HTTP). In Docker the agents use the service names instead.
VIEWERS = {
    "Jaeger": ("JAEGER_OTLP_URL", "http://localhost:4318/v1/traces"),
    "Phoenix": ("PHOENIX_OTLP_URL", "http://localhost:6006/v1/traces"),
}
TRACE_LINKS = {
    "Jaeger": "http://localhost:16686/trace/{}",
    "Phoenix": "http://localhost:6006/redirects/traces/{}",
}
START_VIEWERS = "python scripts/docker_up.py --tracing"
EXPORT_TIMEOUT = 3  # seconds per try, so a viewer that's gone can't hold up the end of a run
# The A2A SDK's internal spans (its event queue and task manager): about 240 per run, no information for
# us. Left out. Its client and server spans stay, and no span we keep has one of these as its parent.
SDK_INTERNALS = ("a2a.server.events.", "a2a.server.tasks.")
CONTENT_BAGGAGE = "cvchecker.record_content"  # the run's permission to record content, sent as W3C baggage
ON_WORDS = ("on", "true", "1", "yes")

# One per process: is tracing on, may content be recorded at all, has the one warning been given.
_state = {"on": False, "content": False, "warned": False, "provider": None, "exporters": {}}


def _setting_on(name: str) -> bool:
    from agents.model_client import read_setting  # here, not at the top: model_client imports this module

    return read_setting(name, "off").strip().lower() in ON_WORDS


def enabled() -> bool:
    return _state["on"]


def warn(message: str) -> None:
    """One warning per process, on stderr."""
    if not _state["warned"]:
        _state["warned"] = True
        print(f"[tracing] {message}", file=sys.stderr, flush=True)


def _running(endpoint: str) -> bool:
    """True if something answers at this address: a quick look, so a missing viewer costs no waiting."""
    parts = urlsplit(endpoint)
    try:
        with socket.create_connection((parts.hostname, parts.port), timeout=0.3):
            return True
    except OSError:
        return False


class ViewerExporter(SpanExporter):
    """An OTLP exporter that never lets a viewer's failure reach the run: it warns once and carries on."""

    def __init__(self, name: str, inner: SpanExporter) -> None:
        self.name, self.inner, self.failed = name, inner, False

    def export(self, spans):
        try:
            result = self.inner.export(spans)
        except Exception:  # noqa: BLE001 - a viewer problem must never become a run problem
            result = SpanExportResult.FAILURE
        if result is not SpanExportResult.SUCCESS:
            self.failed = True
            warn(f"{self.name} didn't take the trace, so it isn't there. The run itself is not affected.")
        return result

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


class SkipSdkInternals(SpanProcessor):
    """Passes every span on to the exporter, except the A2A SDK's internal ones (SDK_INTERNALS)."""

    def __init__(self, inner: SpanProcessor) -> None:
        self.inner = inner

    def on_start(self, span, parent_context=None) -> None:
        self.inner.on_start(span, parent_context=parent_context)

    def on_end(self, span) -> None:
        if not span.name.startswith(SDK_INTERNALS):
            self.inner.on_end(span)

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


def setup(service: str, check_viewers: bool = True) -> bool:
    """Turn tracing on for this process if TRACING=on. Returns whether it's on.

    service: the name this process has in the viewers (e.g. "orchestrator", "cv-matcher").
    check_viewers: look whether the viewers answer first (the orchestrator does; a long-running agent
    doesn't, because in Docker the viewers may start a moment after it).
    """
    if _state["on"]:
        return True
    if not _setting_on("TRACING"):
        return False
    from agents.model_client import read_setting

    # Keep traces on this machine: the Anthropic SDK would otherwise make its own spans and could send
    # our trace id to Anthropic in a request header.
    os.environ["ANTHROPIC_OPEN_TELEMETRY"] = "false"
    os.environ["ANTHROPIC_OPEN_TELEMETRY_PROPAGATION"] = "false"
    logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)  # ViewerExporter gives the one warning

    provider = TracerProvider(resource=Resource.create({"service.name": service, "openinference.project.name": PROJECT}))
    missing = []
    for name, (setting, default) in VIEWERS.items():
        endpoint = read_setting(setting, default)
        if check_viewers and not _running(endpoint):
            missing.append(name)
            continue
        exporter = ViewerExporter(name, OTLPSpanExporter(endpoint=endpoint, timeout=EXPORT_TIMEOUT))
        _state["exporters"][name] = exporter
        provider.add_span_processor(SkipSdkInternals(BatchSpanProcessor(exporter)))
    if missing:
        verb = "is" if len(missing) == 1 else "are"
        warn(f"Tracing is on, but {' and '.join(missing)} {verb} not running, so no trace goes there. "
             f"The run still works. Start the viewers with: {START_VIEWERS}")

    # The GLOBAL provider, on purpose: the A2A SDK's own client and server spans go through it too.
    trace.set_tracer_provider(provider)
    _state.update(on=True, provider=provider, content=_setting_on("TRACE_CONTENT"))
    atexit.register(shutdown)
    return True


def shutdown() -> None:
    """Send what's left. Called at the end of a run (and at exit)."""
    provider, _state["provider"] = _state["provider"], None
    if provider is not None:
        provider.shutdown()


def trace_links(trace_id: str | None) -> list[str]:
    """Where to look for this trace, in each viewer that took it."""
    if not trace_id:
        return []
    return [f"Trace in {name}: {TRACE_LINKS[name].format(trace_id)}"
            for name, exporter in _state["exporters"].items() if not exporter.failed]


# --- Spans -------------------------------------------------------------------------------------------

def tracer():
    return trace.get_tracer("job_cv_checker")


def current_span():
    return trace.get_current_span()


def trace_id_of(span) -> str | None:
    context = span.get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def set_attributes(span, attributes: dict) -> None:
    """Write attributes, leaving out empty ones. Writing down what happened must never change what happens."""
    if not span.is_recording():
        return
    try:
        span.set_attributes({k: v for k, v in attributes.items() if v is not None})
    except Exception as error:  # noqa: BLE001
        warn(f"couldn't record part of a span ({type(error).__name__}).")


def mark_error(span, message: str) -> None:
    """Mark a span as failed, with the reason (shown in red in both viewers)."""
    if span.is_recording():
        span.set_status(Status(StatusCode.ERROR, message))


@contextmanager
def span(name: str, attributes: dict | None = None, kind: SpanKind = SpanKind.INTERNAL):
    """A span around a block. With tracing off it's a no-op span: attributes are dropped, nothing is sent."""
    with tracer().start_as_current_span(name, kind=kind) as current:
        set_attributes(current, attributes or {})
        yield current


# --- Content: only with the switch AND the run's permission --------------------------------------------

def content_switch() -> bool:
    """Is TRACE_CONTENT on (with tracing on)? The orchestrator then decides whether this run may use it."""
    return _state["on"] and _state["content"]


def record_content() -> bool:
    return _state["on"] and _state["content"] and baggage.get_baggage(CONTENT_BAGGAGE) == "on"


def set_content(span, attributes: dict) -> None:
    if record_content():
        set_attributes(span, attributes)


@contextmanager
def allow_content():
    """Orchestrator: allow content recording for this run. The permission travels to the agents as baggage."""
    token = otel_context.attach(baggage.set_baggage(CONTENT_BAGGAGE, "on"))
    try:
        yield
    finally:
        otel_context.detach(token)


# --- Model calls ---------------------------------------------------------------------------------------

@contextmanager
def model_call(model: str, provider: str, system: str | None, prompt: str,
               temperature: float | None = None, max_tokens: int | None = None):
    """A span around one model call, named "chat <model>" as OpenTelemetry's GenAI conventions suggest."""
    attributes = {
        "openinference.span.kind": "LLM",
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": provider,
        "gen_ai.request.model": model,
        "gen_ai.request.temperature": temperature,
        "gen_ai.request.max_tokens": max_tokens,
        "llm.model_name": model,
        "llm.provider": provider,
    }
    with span(f"chat {model}", attributes, kind=SpanKind.CLIENT) as current:
        if record_content():
            messages = ([("system", system)] if system else []) + [("user", prompt)]
            content = {"input.value": prompt}
            for n, (role, text) in enumerate(messages):
                content[f"llm.input_messages.{n}.message.role"] = role
                content[f"llm.input_messages.{n}.message.content"] = text
            set_attributes(current, content)
        yield current


def model_result(span, *, input_tokens: int, output_tokens: int, cost_usd: float, finish_reason: str | None = None,
                 response_model: str | None = None, thinking_tokens: int | None = None) -> None:
    """What a model call used: tokens (standard gen_ai names, and the ones Phoenix reads) and the cost."""
    set_attributes(span, {
        "gen_ai.usage.input_tokens": input_tokens,
        "gen_ai.usage.output_tokens": output_tokens,
        "gen_ai.usage.reasoning.output_tokens": thinking_tokens,
        "gen_ai.response.model": response_model,
        "gen_ai.response.finish_reasons": [finish_reason] if finish_reason else None,
        "llm.token_count.prompt": input_tokens,
        "llm.token_count.completion": output_tokens,
        "llm.token_count.total": input_tokens + output_tokens,
        "llm.cost.total": cost_usd,  # there is no standard gen_ai name for cost yet
        "cvchecker.cost_usd": cost_usd,
    })


def model_answer(span, text: str) -> None:
    set_content(span, {
        "output.value": text,
        "llm.output_messages.0.message.role": "assistant",
        "llm.output_messages.0.message.content": text,
    })


# --- Joining the processes: the trace context in the HTTP headers ---------------------------------------

async def inject_headers(request) -> None:
    """httpx request hook (orchestrator): put the current trace context and baggage into the request headers."""
    if _state["on"]:
        propagate.inject(request.headers)


class TraceContextMiddleware:
    """ASGI middleware (agents): read the trace context and baggage from the request headers, so the agent's
    spans become part of the orchestrator's trace. With tracing off it only passes the request on."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not _state["on"]:
            await self.app(scope, receive, send)
            return
        carrier = {key.decode("latin-1"): value.decode("latin-1") for key, value in scope.get("headers", [])}
        token = otel_context.attach(propagate.extract(carrier))
        try:
            await self.app(scope, receive, send)
        finally:
            otel_context.detach(token)


# --- Agent tasks ---------------------------------------------------------------------------------------

@contextmanager
def agent_task(agent: str, version: str, context, phase: str):
    """A span for one message an agent handles: a new task, or the answer to its question."""
    with span(f"{agent}: {phase}", {
        "openinference.span.kind": "AGENT",
        "cvchecker.agent": agent,
        "cvchecker.agent.version": version,
        "cvchecker.phase": phase,
        "a2a.task.id": context.task_id,
        "a2a.context.id": context.context_id,
    }) as current:
        yield current
