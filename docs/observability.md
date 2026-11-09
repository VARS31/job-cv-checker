# Observability: one trace per run

With tracing on, one pipeline run becomes **one trace**: a tree of timed steps (**spans**) across all five processes, the orchestrator and the four agents. You can open it in two viewers:
- **Jaeger** shows where the time went;
- **Phoenix** shows what each model call read and wrote.

Tracing is **off by default**. Off, nothing is set up and the program behaves exactly as without it.

## How to turn it on

**With Docker** (the agents in containers, the viewers next to them):

```bash
python scripts/docker_up.py --preset haiku --tracing        # or --preset local; add --content for prompts and texts
TRACING=on python -m orchestrator samples/demo/job_ad_demo.txt samples/demo/cv_jane_doe.pdf \
    --answers samples/demo/answers_jane_doe.json
python scripts/docker_up.py --down                           # stop everything
```

**Without Docker:**

```bash
docker compose --profile tracing up -d jaeger phoenix        # only the viewers
TRACING=on python scripts/start_agents.py                    # terminal 1
TRACING=on python -m orchestrator ...                        # terminal 2
```

Instead of `TRACING=on` in front of each command, you can put `TRACING=on` in `.env`.

At the end of a run, the orchestrator prints the trace's address in each viewer:

```
Trace in Jaeger: http://localhost:16686/trace/<trace id>
Trace in Phoenix: http://localhost:6006/redirects/traces/<trace id>
```

The trace id is also saved in the run's `run_log.json`.

**Ports:** the viewers use the same ports as the labour-law project's viewers: 16686 and 4318 for Jaeger, 6006 for Phoenix. Only one set can run at a time, so stop the other project's viewers first:

```bash
docker compose --profile observability stop jaeger phoenix   # in the labour-law project
```

`docker_up.py` checks the ports first and says which one is busy.

## The two switches

| Setting | Default | What it does |
|---|---|---|
| `TRACING` | off | Spans for the run, the steps, the A2A calls, the model calls (model, tokens, cost), the grounding checks and the waits. **No texts.** |
| `TRACE_CONTENT` | off | Also the texts: prompts (with the CV text), model answers (the letter), and your answers to the agents' questions. |

**Content is recorded only with both keys:**
1. the process's own `TRACE_CONTENT=on`;
2. the run's permission. The orchestrator gives it **only for the fictional CVs in `samples/demo/`**, and refuses to run with `TRACE_CONTENT=on` and any other CV.

The permission travels to the agents as W3C *baggage* (a header next to the trace context). An agent records texts only for a run that carries it, so even an agent started with `--content` never records a real CV.

**What never goes into a span:**
- **The API key.** Nothing in the tracing code reads it. The Anthropic SDK's own tracing, which could also send our trace id to Anthropic, is switched off (`ANTHROPIC_OPEN_TELEMETRY=false`).
- **File names,** unless content recording is on (a CV's file name can contain a person's name).

**Viewers down:** the run still works. You get one warning (`[tracing] ... not running, so no trace goes there`), and the spans for that viewer are dropped.

## What's in a trace

Run C from the demo below: Jane Doe (fictional), Claude Haiku, answers typed through the terminal after real pauses. The A2A SDK's own client and server spans sit between each "send_message" and the agent's span; they're folded here.

```
pipeline run                                    orchestrator          76.4 s
├─ step 1: Job Analyst                          orchestrator           6.0 s
│  └─ A2A send_message  ──────────────────────▶ job-analyst
│     └─ Job Analyst: new task                  job-analyst            6.0 s
│        └─ chat claude-haiku-5-5               job-analyst            6.0 s   4,311 tokens in, 1,496 out, $0.0012
├─ step 2: CV Matcher                           orchestrator          18.8 s
│  ├─ A2A send_message  ──────────────────────▶ cv-matcher
│  │  └─ CV Matcher: new task                   cv-matcher             7.7 s
│  │     ├─ chat claude-haiku-5-5               cv-matcher             7.7 s   2,578 in, 2,077 out, $0.0013
│  │     └─ grounding: CV quote check           cv-matcher             0.0 s   16 found, 1 asked (travel)
│  ├─ waiting for the user: CV Matcher          orchestrator          11.1 s   ← the human-in-the-loop pause
│  └─ A2A send_message  ──────────────────────▶ cv-matcher
│     └─ CV Matcher: answers received           cv-matcher             0.0 s   waited 11.07 s
├─ step 3: Cover Letter Writer                  orchestrator          33.7 s
│  ├─ … new task (asks "why this role?")
│  ├─ waiting for the user: Cover Letter Writer orchestrator           8.0 s
│  └─ A2A send_message  ──────────────────────▶ cover-letter-writer
│     └─ Cover Letter Writer: answer received   cover-letter-writer   25.7 s   waited 7.98 s
│        ├─ chat claude-haiku-5-5               cover-letter-writer   25.7 s   3,773 in, 6,817 out, $0.0038
│        └─ grounding: claims check             cover-letter-writer    0.0 s   13 proven, 0 unproven
└─ step 4: Application Reviewer                 orchestrator          17.7 s
   └─ A2A send_message  ──────────────────────▶ application-reviewer
      └─ Application Reviewer: new task         application-reviewer  17.7 s
         ├─ chat claude-haiku-5-5               application-reviewer  17.7 s   5,924 in, 4,127 out, $0.0027
         ├─ grounding: letter quote check       application-reviewer   0.0 s   2 overclaims kept, 0 dropped
         └─ cliché check                        application-reviewer   0.0 s   0 added
```

| Span | Where | What it records |
|---|---|---|
| `pipeline run` | orchestrator | run folder, A2A context id, where answers came from; at the end the status, total tokens and cost |
| `step n: <agent>` | orchestrator | agent, version, state, task id, model, tokens, cost (the agent's own report), seconds |
| `a2a.client...send_message` | orchestrator | the A2A SDK's client span. The trace context leaves in its HTTP headers |
| `a2a.server...JsonRpcDispatcher...` | agent | the A2A SDK's server spans, children of the client span in another process |
| `<agent>: new task` / `answers received` | agent | task and context id, version; after a pause, `cvchecker.hitl.waited_seconds` |
| `chat <model>` | agent | `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.usage.input_tokens` / `output_tokens`, `gen_ai.response.finish_reasons`; cost as `llm.cost.total`; with content: the messages and the answer |
| `grounding: ...`, `cliché check` | agent | what the plain-Python checks kept, dropped or changed (counts; with content, the unproven claims) |
| `waiting for the user: <agent>` | orchestrator | how long the run waited for your answers, how many questions, terminal or file; with content, the questions and answers |

With scripted answers (`--answers`), the waits are a few milliseconds. With you at the terminal, they show how long you took.

**Attribute names:**
- `gen_ai.*` are OpenTelemetry's standard GenAI names. There is no standard name for cost yet.
- `openinference.*`, `llm.*`, `input.value` and `output.value` are what Phoenix reads to recognise LLM spans.
- `cvchecker.*` are this project's own.

## What to look at in each viewer

**Jaeger** (<http://localhost:16686>) shows time and the path through the services.
- Open a printed link, or use **Search** with the service `orchestrator`. One trace lists all five services.
- The timeline shows where the time went at a glance. In run C, the letter (25.7 s) and the two waits for the user (11.1 s and 8.0 s) are the longest bars.
- Click a `chat claude-haiku-5-5` span for model, tokens and cost. Jaeger recognises the `gen_ai.*` names (there's a GenAI view at the top right).
- To check the processes are joined: each agent's server span hangs under the orchestrator's `send_message` span, with a different service colour.

**Phoenix** (<http://localhost:6006>) shows the model calls and their content.
- Open a printed link, or go to **Tracing** and the project `job-cv-checker`. All five services' spans land in this one project.
- Each `chat` span shows as an LLM span, with its tokens and cost.
- In a run with content (B or C below), clicking a `chat` span shows the prompt (the CV text, the matched requirements) and the model's answer (the letter as JSON).
- Filters to try:

```
span_kind == 'LLM'
llm.model_name == 'claude-haiku-5-5'
attributes['cvchecker']['hitl']['waited_seconds'] > 5
status_code == 'ERROR'
```

## How it works

- **One setup module,** `agents/tracing.py`, for the orchestrator and all four agents (each gets its own `service.name`). It sets the **global** OpenTelemetry provider, so the A2A SDK's own client and server spans are included.
- **The SDK makes spans, but doesn't pass the trace context between processes.** So the orchestrator's httpx client puts it into every request's headers (an httpx request hook, `traceparent` and `baggage`). Each agent's server reads it back (an ASGI middleware in `agents/server.py`) before the SDK's server spans start.
- **The SDK's internal spans are left out.** Its event queue and task manager make about 240 spans per run with nothing for us. A span processor drops them; the client and server spans stay, and no kept span loses its parent. A run has about 75 spans.
- **Two exporters, one per viewer,** both OTLP over HTTP. Each warns once if its viewer doesn't take a batch, and never raises into the run.

## Demo traces (2026-11-09)

Jane Doe (fictional) with Claude Haiku in Docker, tracing on:

| Run | Content | Answers | Trace id | Cost |
|---|---|---|---|---|
| A | off (the agents' switch was on, but no permission) | scripted | `790c698c326f7d8f4d3ddd3b07e368d1` | $0.0079 |
| B | on | scripted | `4400c0aa486b69d2ce552257cad6860c` | $0.0073 |
| C | on | typed through the terminal after real pauses | `41450742b125120ec3992660baf44845` | $0.0089 |

**Checked through Jaeger's API:**
- all three traces have 75 spans across 5 services and no span without its parent;
- run A has no texts at all (not even the name "Jane Doe");
- B and C have prompts, letters and answers;
- no trace contains `sk-ant-`;
- the model inputs start with today's date.

Jaeger keeps traces in memory and Phoenix in its container, so these trace ids only open while that stack is running.

## Limits

- **For learning and demos, not production:** no sampling, no retention, no authentication. The viewers listen on 127.0.0.1 only.
- **SDK-specific filtering:** the A2A SDK's span names (and the filter on them) belong to `a2a-sdk` 1.2.3 and may change with a new version.
- **One-sided runs:** the orchestrator and the agents decide about tracing separately. If only one side has it on, the trace has only that side's spans.
