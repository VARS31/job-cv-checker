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

- **A different model** (`granite4.1:8b`, temperature 0) than the writer (`ministral-3:8b`), so the reviewer doesn't share the writer's blind spots. It also had 0 invented facts in the Job Analyst comparison. (With `--preset haiku`, all four agents use the same model family; see decision 5 and the README's known limitations.)
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
  - `scripts/start_agents.py --preset local|haiku` sets all four at once (default `local`), so switching is one flag.
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
