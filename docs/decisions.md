# Decisions

## 1. Fixed routing instead of model-based routing

The orchestrator calls the agents in a fixed order written in Python, rather than letting a model decide which agent to call next. This keeps the flow predictable and easy to debug while learning A2A.

## 2. Local models via Ollama behind one swappable model client

All model calls go through a single model-client module that talks to Ollama on `localhost:11434`. This keeps the project free of paid APIs and means we can swap the model or provider by changing one file. (Decision 5 later added Claude as an optional second provider behind the same module; local stays the default.)

## 3. The orchestrator is a fixed list of pipeline steps

The pipeline is always Job Analyst → CV Matcher → Cover Letter Writer → Application Reviewer, so the order is a plain Python list (`orchestrator/pipeline.py`), not a decision made at run time. Each step is a small object that says:
- which agent it calls (URL from `.env`, plus the command to start it);
- how to build the agent's message from the results so far;
- how to read the agent's artifact into new results;
- which output files to save.

The orchestrator loop itself knows nothing about specific agents. Adding an agent means writing one more step and appending it to the list; the loop, the input-required handling and the run saving stay unchanged. The fourth agent, the Application Reviewer, was added exactly this way (decision 4).

Other choices that follow from this:
- **Fail fast:** all agent cards are read before any work starts. A missing agent costs a second, not a half-finished run.
- **One generic input-required handler:** agents describe their questions in the A2A message itself (a data part with question ids means yes/no, otherwise free text). The orchestrator needs no agent-specific code to answer them. At most 3 rounds per agent, so a confused agent can't loop forever.
- **One context id per run:** every task in a run belongs to the same A2A context. The SDK accepts a new task with a client-chosen context id, and only checks that follow-ups match their task's context.
- **Stop on failure, keep what's done:** each step's outputs and the run log are written as soon as the step finishes, so a failed run still shows how far it got and why.

## 4. The Application Reviewer only reports, with a different model

The fourth agent reviews the whole application like a senior recruiter: verdict, top weaknesses, overclaims, generic sentences, company specificity and likely interview questions. It never rewrites the letter, so it can't introduce new unproven claims, and its findings stay a second opinion for the user.

- **A different model** (`granite4.1:8b`, temperature 0) than the writer (`ministral-3:8b`), so the reviewer doesn't share the writer's blind spots. It also had 0 invented facts in the Job Analyst comparison. (With `--preset haiku`, all four agents use the same model family; `--preset haiku-sonnet` gives the Reviewer a different one again, see decision 8.)
- **No score, a verdict.** "Shortlist / maybe / reject" plus one sentence is what a recruiter actually decides. The CV Matcher already gives the percentage.
- **Grounded quotes.** Every overclaim and generic sentence must be quoted from the letter. Plain Python checks each quote with the shared quote check, drops the ones that aren't in the letter, and counts them in `dropped_ungrounded`.
- **Model plus a plain-Python safety net.** The letter is given to the model as numbered sentences, so it judges each one. A short list of known clichés ("perfect fit", "I thrive"…) is also checked in plain Python, because even at temperature 0 a small model skips sentences.

**Extensibility check:** adding this agent to the pipeline needed one new step in `orchestrator/pipeline.py` and one line in `scripts/start_agents.py`. A one-time refactor moved the end-of-run summary lines into the steps, so the next agent won't need any change in `orchestrator/__main__.py` either.

## 5. Local by default, cloud optional; the model belongs to the agent

Claude Haiku can now run any agent. The local models stay the default, and the cloud is an explicit opt-in.

- **The model belongs to the agent.** In A2A, agents are opaque: a client sees an agent card and results, not the model behind them.
  - Each agent reads its model from its settings once, at startup (`JOB_ANALYST_MODEL` and so on).
  - It reports the model, tokens and cost in its result metadata (`model_usage`).
  - The orchestrator records that per step in `run_log.json`, but never chooses a model.
  - `scripts/start_agents.py --preset local|haiku` sets all four at once (default `local`), so switching is one flag. A third preset, `haiku-sonnet`, came later (decision 8).
- **The name decides the provider.** A name starting with `claude-` means Claude; anything else means Ollama. Both sit behind the same `ask_model()` in `agents/model_client.py`, so the agents and the prompts didn't change.
- **No silent fallback.**
  - An agent with a Claude model checks `ANTHROPIC_API_KEY` at startup, with a free model lookup.
  - If the key is missing or rejected, it says so and doesn't start. It never quietly switches to a local model, because that would change both the results and where the data goes.
  - The key is never printed, logged or stored.
- **A budget guard, shared by four processes.**
  - Every Claude call is checked before it's made (at its worst-case cost) and counted after it (real usage), in `results/cloud_spend.json`.
  - The limits are $0.50 per run and $3.00 in total, configurable in `.env`.
  - The agents take turns on the file under a lock, and the file is replaced in one atomic step, so no count is lost.
  - A stopped call fails its step, and the orchestrator stops cleanly, keeping what's finished.
- **Same prompts and schemas, two differences, written down:**
  - **Temperature.** The API version the SDK uses (2026-10-21) rejects `temperature` on every model, and Haiku 5.5 runs adaptive thinking by default. So Claude runs at its defaults, and its runs are not exactly repeatable. The local models keep their temperatures (0, and 0.4 for the letter).
  - **Schemas.** Claude's native structured output takes the same JSON schemas, but it doesn't enforce array lengths (`maxItems`, `minItems` above 1). The adapter converts the schema with the SDK's `transform_schema()`, which moves those limits into the field descriptions, then checks them in plain Python. Too many items are cut, as Ollama's grammar would; too few fail the step. The alternative, separate Claude-only schemas, would drift apart from the Ollama ones.
- **Data leaves the machine with Claude.** The job ad, the CV text, the letter and the user's answers go to Anthropic, so the README says so first. Measuring runs use only the fictional demo CV.

The comparison that came with this step is in [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md).

## 6. Preferred fields for experience and other requirements; ask what a CV can't show; the Reviewer reads the ad

Step 1 showed three gaps (see [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md)). Step 1.1 fixed them:

- **Two new schema fields, `experience_preferred` and `other_requirements_preferred`**, following the existing pattern of required and preferred hard skills.
  - Before, the schema had preferred *skills* only. Preferred experience and certificates had nowhere to go, so models put them in required fields, Haiku with "(preferred)" written into the item.
  - Now nice-to-haves go into these fields, and an empty list means none. The CV Matcher scores them as preferred (1 point).
  - The marker clean-up stays as a safety net and now runs on all three required lists. In the re-run it didn't have to move anything.
  - **Result:** wrong-field items on 10 ads went from 5 (local) and 10 (Haiku) to 0 for both.
- **What a CV can't show is always asked.** Willingness to travel or relocate, a start date, availability and shifts are matched by keywords in plain Python.
  - Such an item is never "missing", only "unclear", and these questions come first, even for preferred items.
  - Plain Python, not a prompt rule, because it must hold for every model.
  - **Result:** travel was asked in 7 of 8 end-to-end runs. In the 8th, the Job Analyst hadn't listed travel at all.
- **The Reviewer gets the original job ad** (with the company description) as a labelled text part, next to the Job Analyst's fields.
  - Without it, the Reviewer flagged true company facts as overclaims, and couldn't spot false ones.
  - The two text parts (letter and ad) are told apart by part metadata (`{"content": "job_ad"}`), which keeps it plain A2A.

**The Reviewer result** (a tiny planted-error test, details in the comparison):
- Haiku caught 3 of 4 planted mistakes in both runs. It missed the irrelevant claim.
- Sonnet (`claude-sonnet-5-5`) caught all 4 in both runs, at about 15 times the cost per review ($0.035 against $0.0024). Neither raised a false alarm.
- The wrong company fact was caught by every run, which the new ad-text input made possible.

Nothing is decided from four runs: the presets stay as they are. A mixed set-up (Haiku agents, Sonnet Reviewer) and giving the Reviewer today's date went on the backlog. Both followed later: today's date in decision 7, the mixed preset in decision 8.

**No refusal fallback for Sonnet.** The API can retry a refused request on another model. The adapter doesn't use that, because it would switch models silently and the budget guard prices each call by model. A refusal fails the step with a clear message instead.

## 7. Docker and OpenTelemetry: optional, lean, and private by default

Step 2 added a way to run the agents in containers and to see one run as one trace. Both are optional: `start_agents.py` and the plain commands work as before, and tracing is off by default. Details: [observability.md](observability.md).

**Docker:**
- **One image for all four agents** (same code, a different command per container), defined in one `docker-compose.yml`. The viewers (Jaeger, Phoenix) sit behind a `tracing` profile, so they start only when asked.
- **Ollama stays on the Mac** (containers reach it via `host.docker.internal`), and the orchestrator stays in the terminal, because it asks the user questions.
- **Everything is published on 127.0.0.1 only.** Inside a container an agent listens on 0.0.0.0, but its agent card keeps saying `http://localhost:<port>`.
- **Nothing private reaches the image.**
  - `.dockerignore` denies everything and allows only `agents/`, `prompts/` and `requirements.txt`. The image was listed after the build: no `.env`, no CVs, no results, no key.
  - The key reaches the containers only as an environment variable at start, and only with a Claude preset (`haiku` or `haiku-sonnet`).
- **The preset is chosen at start** (`docker_up.py --preset local|haiku|haiku-sonnet`, default local), with the same presets as `start_agents.py`.
- **The budget lock had to change.** The four containers share `results/` with the Mac, but `fcntl.flock` doesn't reach across containers on Docker Desktop's file sharing (tested: two containers both got it). The guard now uses a lock file created with `O_CREAT|O_EXCL`, which is exclusive across containers and the Mac (tested), with stale-lock removal.

**Tracing:**
- **One shared setup module** (`agents/tracing.py`) for the orchestrator and all four agents. It sets the global OpenTelemetry provider on purpose, so the A2A SDK's own client and server spans are part of the trace.
- **The trace context is passed by hand.** The SDK doesn't carry it between processes, so the orchestrator's httpx client injects it into the HTTP headers and an ASGI middleware in each agent extracts it. One run is then one trace across five services.
- **The SDK's internal event-queue and task-manager spans are dropped** (about 240 of 319 in the first traced run); the client and server spans stay, and no kept span loses its parent.
- **What gets spans:** a span per model call with OpenTelemetry's standard `gen_ai.*` names (model, tokens) and the cost as `llm.cost.total`, since there's no standard name for cost yet; spans for the grounding checks; and the human-in-the-loop pause on both sides (the orchestrator's wait span, and the agent's `waited_seconds`).
- **Content needs two keys:** `TRACE_CONTENT=on` *and* the run's permission. The orchestrator gives the permission only for the fictional CVs in `samples/demo/` and passes it as W3C baggage. So an agent never records a real CV's text, even when its own switch is on. Tested end to end: with the agents' switch on but no permission, the trace had no texts at all.
- **Never in a span:** the API key (nothing reads it; the Anthropic SDK's own tracing and trace propagation are off), and file names unless content is on.
- **A viewer that's down costs one warning,** never the run.

**Today's date** now goes into the inputs of the agents that read CVs (CV Matcher, Cover Letter Writer, Reviewer), so "09/2019 - today" is counted from the real date. The Reviewer had miscounted it in step 1.1.

## 8. A third preset: Haiku agents, Sonnet Reviewer

`--preset haiku-sonnet` runs Claude Haiku for the Job Analyst, CV Matcher and Cover Letter Writer, and Claude Sonnet for the Application Reviewer. The default stays `local`.

- **Why:**
  - With `--preset haiku`, the Reviewer is the same model family as the agents whose work it reviews, so it may share their blind spots. Locally that never happens: the Reviewer is `granite4.1:8b` and the others are `ministral-3:8b` (decision 4).
  - A Reviewer from another family is the cheapest step back to a second opinion, and it changes nothing else.
  - The tiny planted-error test pointed the same way (decision 6): Sonnet caught all 4 mistakes in both runs, including the irrelevant claim; Haiku caught 3 of 4.
- **The same safety as the other Claude preset:** every agent checks `ANTHROPIC_API_KEY` and its own model at startup (a free model lookup), and every call goes through the budget guard. Sonnet's price was checked on the live pricing page before the guard used it ($2 / $10 per million tokens, 2026-11-09).
- **Cost and speed** (one Jane Doe run with scripted answers, 2026-11-09):
  - $0.038 in 44 s, of which the Sonnet review was $0.034;
  - about five times the `haiku` preset ($0.006–$0.009 per run);
  - `local` costs nothing.
- **Why it's an option, not the default:** it costs money and sends the job ad, the CV text and the letter to Anthropic, like any Claude preset. And the evidence is a tiny test (one letter, two runs per model), not a measurement.

