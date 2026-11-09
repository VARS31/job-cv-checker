# Job Ad & CV Checker

A small multi-agent system that reads a job ad, checks a CV against it, writes an honest cover letter, and reviews the whole application like a recruiter would. The agents talk to each other with the **A2A (Agent-to-Agent) protocol**. They run on **local models via Ollama by default**: no paid APIs, and no data leaves the machine. **Claude Haiku is optional** for any agent (cloud, paid; see [Models](#models)).

> **Privacy warning: with Claude Haiku, your data goes to Anthropic.** When an agent uses a Claude model (for example with `--preset haiku`), the **job ad and the full text of the CV** are sent to Anthropic's API, and so are the cover letter and your answers to the agents' questions. Keep the default local models for any CV that shouldn't leave your machine.

I built it as a learning project for A2A and multi-agent design, so the code is deliberately small and commented at every A2A concept (agent card, task, status, artifact, input-required).

> **Status:** all four agents and the orchestrator work end to end with one command, on local models or on Claude Haiku. Ideas for what comes next are in [docs/backlog.md](docs/backlog.md).

## What it does

1. **Job Analyst**: reads a job ad and returns its requirements as structured JSON: job title, company, education, years of experience, hard skills, soft skills, languages, responsibilities, travel and certifications. Skills, experience and other requirements each come as a required and a preferred list.
2. **CV Matcher**: takes those requirements plus a CV (PDF) and checks every requirement against the CV:
   - Each item is **found** (with an exact quote from the CV as proof), **missing**, or **unclear**.
   - What a CV can't show (willingness to travel or relocate, start date, availability) is never "missing": it's **unclear**, so the candidate is asked.
   - If items are unclear, the task **pauses** and asks the user up to 5 yes/no questions (A2A `input-required`): the things a CV can't show first, then unclear required items. The answers continue the same task.
   - The result is a match score (required items count 2, preferred count 1) and a short report.
3. **Cover Letter Writer**: asks the user one free-text question ("why this role?"), then writes a three-paragraph letter from the matched and confirmed items only:
   - Every factual claim must come with an exact quote from the CV or from the user's answer, checked in plain Python. Unproven claims trigger one rewrite.
   - A plain-Python style check fixes dashes and warns about buzzwords, length and structure.
4. **Application Reviewer**: acts as a senior recruiter for the job (locally a different model, `granite4.1:8b`, at temperature 0). It reads the original job ad, including the company description, next to the Job Analyst's requirements, and only reports, never rewrites:
   - a verdict (shortlist / maybe / reject) with a one-sentence reason, the top 3 weaknesses, overclaims and generic sentences in the letter, whether paragraph 3 is company-specific, and 3 to 5 likely interview questions;
   - every quoted letter sentence is checked in plain Python against the letter, and items that don't match are dropped and counted. A plain-Python list of known clichés backs up the model.
5. **Orchestrator**: runs all four in a fixed order with one command, answers the agents' questions through the terminal (or from a file, for repeatable runs), and saves the whole run, with the model, tokens, cost and time of every step.

## Architecture

```
   job ad (text) + CV (PDF)
              │
              ▼
   ┌───────────────────────────────┐        results/runs/<date-time>/
   │ Orchestrator: plain Python,   │ ─────▶ requirements, match report, letter,
   │ fixed routing, one context id │        claims, review, run log
   └───────────────┬───────────────┘
                   │  A2A (JSON-RPC over HTTP), one step after the other
     ┌─────────────┼───────────────┬───────────────────┐
     ▼             ▼               ▼                   ▼
   1 Job Analyst 2 CV Matcher    3 Cover Letter      4 Application
     :9001         :9002           Writer :9003        Reviewer :9004
     ad → JSON     JSON + PDF      JSON + PDF +        everything →
     require-      → score,        answer → letter     verdict, overclaims,
     ments         y/n questions   + checked claims    interview questions
     │             │               │                   │
     └─────────────┴───────┬───────┴───────────────────┘
                           ▼
               agents/model_client.py   (the only place that calls a model)
                ▼ default                         ▼ optional, paid
   Ollama on this machine              Anthropic API (budget guard)
   (ministral-3:8b, granite4.1:8b)     (claude-haiku-5-5)
```

- **A2A:** each agent is its own HTTP server with a public **agent card** at `/.well-known/agent-card.json`. Requests create **tasks** with a status (`working`, `input-required`, `completed`, `failed`). Results come back as **artifacts** made of **parts** (text, structured data, or files).
- **Orchestrator:** reads all agent cards first and stops with a clear message if one isn't running. Each step passes the earlier artifacts on to the next agent. One generic handler answers every agent's `input-required` pause: y/n for questions with ids, free text otherwise.
- **One model client:** every model call goes through `agents/model_client.py`. The model name decides where it goes: `claude-...` to Anthropic, anything else to Ollama. It sets the JSON schema and a timeout. For Ollama it also sets the context size (8192) and the temperature, and warns when a request gets close to the context limit. For Claude it applies the budget guard. Each agent reports the model, tokens and cost in its result metadata.
- **Prompts as files:** each agent's instructions live in `prompts/*.md`, so they can be edited without touching code. Local and Claude get the same prompts.

## Models

**Local by default, cloud optional.** The model belongs to the agent: each agent reads its model from its settings when it starts. Other agents and the orchestrator only see what it reports back (A2A agents are opaque).

| Agent | Setting in `.env` | `--preset local` (default) | `--preset haiku` |
|---|---|---|---|
| Job Analyst | `JOB_ANALYST_MODEL` | `ministral-3:8b` | `claude-haiku-5-5` |
| CV Matcher | `CV_MATCHER_MODEL` | `ministral-3:8b` | `claude-haiku-5-5` |
| Cover Letter Writer | `COVER_LETTER_MODEL` | `ministral-3:8b` | `claude-haiku-5-5` |
| Application Reviewer | `REVIEWER_MODEL` | `granite4.1:8b` | `claude-haiku-5-5` |

- **Choosing:**
  - `python scripts/start_agents.py --preset local|haiku` sets all four at once; the default is `local`.
  - An agent started on its own (`python -m agents.<name>`) uses its line in `.env`.
  - A name starting with `claude-` means Claude; anything else means Ollama (`OLLAMA_URL`).
- **Key check:** an agent with a Claude model checks `ANTHROPIC_API_KEY` when it starts, with a free model lookup. If the key is missing or rejected, the agent prints a clear message naming `ANTHROPIC_API_KEY` and doesn't start. It never falls back to a local model, and the key is never printed or logged.
- **Budget guard:**
  - Every Claude call is checked before it's made and counted right after it, with real usage. The totals live in `results/cloud_spend.json` (gitignored).
  - The limits are $0.50 per run and $3.00 in total (`BUDGET_PER_RUN_USD`, `BUDGET_TOTAL_USD`). A call that could pass a limit isn't made; the step fails and the orchestrator stops cleanly.
  - The four agent processes take turns on the file, under a lock.
  - To start a new budget period (e.g. a new upgrade step), move the file away, e.g. to `results/cloud_spend_step1.json`, and set the limit for the step in `.env`.
- **What is different on Claude:**
  - **No temperature.** The API version the SDK uses no longer accepts one, so Haiku runs at its defaults (adaptive thinking, default effort), and its runs aren't exactly repeatable.
  - **Adapted schemas.** The JSON schemas are the same, but the API doesn't enforce array lengths. Those limits go into the field descriptions and are checked in plain Python afterwards.
  - **Prices** (checked on Anthropic's pricing page), per million tokens, thinking counted as output:
    - Claude Haiku 5.5: $0.10 in, $0.50 out (2026-11-08);
    - Claude Sonnet 5.5: $2 in, $10 out (2026-11-09; used only in the Reviewer test).

**Local vs Haiku** (full write-up, before and after the step 1.1 fixes: [docs/comparison-local-vs-haiku.md](docs/comparison-local-vs-haiku.md)).
- The Job Analyst numbers use the existing scorecard (strict reading) on 7 real AI job ads. "After" scores are model-read, pending a human spot-check.
- End to end means fictional CVs with scripted answers, compared with expected outcomes written before the runs.

| | Local | Haiku |
|---|---|---|
| Job Analyst, 7 ads: wrong field, before → after the fixes | 3 → **0** | 7 → **0** |
| Job Analyst, 7 ads: vague items / invented facts, after | 15 / 0 | 5 / 0 |
| Job Analyst: seconds per ad, cost per ad | 24 s, $0 | 8 s, ~$0.001 |
| Dummy CVs (expected: strong 85–100% shortlist, medium 55–75% maybe, weak 0–20% reject) | 100% shortlist, 74% maybe, 10% reject | 100% shortlist, 76% maybe, 3% reject |
| Same strong CV run 3 times (Haiku) | | score 100% each time; verdict shortlist, maybe, shortlist |
| End-to-end time, cost per run (average) | 2.4 min, $0 | 53 s, $0.0075 |

Both models now put preferred experience and certificates in the right fields. Haiku writes cleaner requirement lists and is about three times faster. Its verdicts vary between runs of the same application, though.

## Project layout

```
orchestrator/
  __main__.py            one command for the whole pipeline (--answers FILE for scripted answers)
  pipeline.py            the fixed list of steps (add an agent = add one step)
  agent_runner.py        agent cards, sending messages, the generic input-required handler, usage per step
  answers.py             where answers come from: the terminal, or a JSON file
  run_store.py           saves each run to results/runs/<date-time>/
agents/
  model_client.py        the only module that talks to a model (Ollama or Claude), plus the startup check
  budget.py              the budget guard for Claude calls (prices, limits, the shared spend file)
  cv_text.py             shared: CV PDF to text, and the quote check
  job_analyst/           agent 1 (port 9001): __main__.py = server + logic, schema.py = JSON shape + clean-up
  cv_matcher/            agent 2 (port 9002): __main__.py, schema.py (checklist, questions), scoring.py
  cover_letter_writer/   agent 3 (port 9003): __main__.py, schema.py (claims check, style check)
  application_reviewer/  agent 4 (port 9004): __main__.py, schema.py (rubric schema, grounding, cliché check, review.md)
prompts/                 agent instructions (Markdown)
scripts/                 start_agents.py (--preset local|haiku), run_all_samples.py, try_*.py for single agents
tests/                   pytest suite: plain-Python logic only (no models, no network, no personal files)
samples/                 put your own job ads (*.txt) and CVs (cvs/*.pdf) here; not committed
  demo/                  fictional demo CV, job ads and scripted answers; committed
results/                 runs, evaluation output and the cloud spend file; not committed
docs/                    decisions, model comparisons, backlog
```

## How to run

**You need:** Python 3.11, [Ollama](https://ollama.com), and about 12 GB of disk space for the two models.

```bash
# 1. Get the local models
ollama pull ministral-3:8b
ollama pull granite4.1:8b

# 2. Set up Python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure (models, Ollama URL, agent URLs; optionally ANTHROPIC_API_KEY)
cp .env.example .env

# 4. Check the plain-Python logic (no models needed)
python -m pytest
```

**The whole pipeline.** Use two terminals, both with the venv activated:

```bash
python scripts/start_agents.py                                   # terminal 1: starts all four agents (local); Ctrl+C stops them
python -m orchestrator samples/my_job_ad.txt samples/cvs/my_cv.pdf   # terminal 2: the pipeline
```

**With Claude Haiku** (cloud, paid; the job ad and CV text go to Anthropic): put your key in `.env` as `ANTHROPIC_API_KEY=...`, then start the agents with `python scripts/start_agents.py --preset haiku`.

The orchestrator prints one progress line per agent (with its model and, for Claude, the cost). It asks the CV Matcher's yes/no questions and the Cover Letter Writer's question in the terminal, and saves everything in `results/runs/<date-time>/`:
- `requirements.json`, `match_report.json`;
- `cover_letter.md`, and `claims.json` with the checked claims and style warnings;
- `review.md` and `review.json` from the Application Reviewer;
- `run_log.json`:
  - per step: the task id, final state, model, tokens, cost, seconds, and every question asked with its answer;
  - the totals for the run.

**Repeatable runs:** `--answers FILE` takes the answers from a JSON file instead of the terminal. Questions are matched by the words they contain, not by their ids, so a local run and a Haiku run get the same answers. Example and format: `samples/demo/answers_demo.json` and `orchestrator/answers.py`.

**Single agents** (for testing one agent at a time):

```bash
python -m agents.job_analyst                                   # terminal 1: agent on :9001
python scripts/try_job_analyst.py samples/my_job_ad.txt        # terminal 2: one ad
python -m scripts.run_all_samples                              # terminal 2: all ads in samples/ → results/<model>/
python -m scripts.run_all_samples samples/demo/*.txt --out results/compare   # chosen ads, another folder

python -m agents.cv_matcher                                    # agent on :9002
python scripts/try_cv_matcher.py results/ministral-3_8b/my_job_ad.json samples/cvs/my_cv.pdf

python -m agents.cover_letter_writer                           # agent on :9003
python scripts/try_cover_letter.py results/ministral-3_8b/my_job_ad.json results/cv_matcher/my_job_ad__my_cv.json samples/cvs/my_cv.pdf

python -m agents.application_reviewer                          # agent on :9004
python -m scripts.try_reviewer results/runs/<date-time>       # review an existing run again (--letter: another letter)
```

These `try_*` scripts are interactive tools, not automated tests: they print the raw A2A JSON of each step. You can see an agent card in the browser at http://localhost:9001/.well-known/agent-card.json (or `:9002`, `:9003`, `:9004`).

Set `MODEL_DEBUG=true` in `.env` to save the exact requests sent to a local model in `results/<model>/prompts/`.

## Demo (fictional data)

`samples/demo/` contains a made-up CV (`cv_demo.pdf`, a mid-level backend & AI engineer called "Jordan Example") and a made-up job ad (`job_ad_demo.txt`, "Backend & AI Engineer" at the fictional Lumenpath Logistics). None of it is real; the PDF is generated by `scripts/make_demo_cv.py`.

```bash
python scripts/start_agents.py                                                   # terminal 1
python -m orchestrator samples/demo/job_ad_demo.txt samples/demo/cv_demo.pdf     # terminal 2
# or, with the fictional candidate's scripted answers (no typing):
python -m orchestrator samples/demo/job_ad_demo.txt samples/demo/cv_demo.pdf --answers samples/demo/answers_demo.json
```

Measuring runs (model comparisons) use only these demo files, never a real CV:
- **Three more fictional CVs** for the same ad, made by the same script:
  - `cv_jane_doe.pdf`: strong fit;
  - `cv_robin_sample.pdf`: medium fit;
  - `cv_casey_placeholder.pdf`: weak fit.

  Each has its own scripted answers (`answers_<name>.json`), and their expected outcomes were written before any run (`expected_outcomes.md`).
- **`planted_errors/`:** a tiny Reviewer test, a letter with 4 planted mistakes (see [the comparison](docs/comparison-local-vs-haiku.md#c-planted-errors-a-tiny-reviewer-test-step-11)).

An excerpt of a real run (answers given as the fictional candidate: "yes" to SQL, PostgreSQL and CI/CD, which the CV lists):

```
→ Job Analyst: working… completed (19 s)
→ CV Matcher: working… input-required (3 questions)
→ CV Matcher: working… completed (23 s)
→ Cover Letter Writer: working… input-required (free text)
→ Cover Letter Writer: working… completed (64 s)
→ Application Reviewer: working… completed (32 s)

  Match score: 87%
  Verdict: shortlist (All core required skills are clearly demonstrated in the CV and
           confirmed by the candidate, with credible proof in the cover letter.)
```

Two of the reviewer's findings from the same run:
- **Top weakness:** "Occasional customer travel is not mentioned" *(requirement: occasional customer travel, ~10%)*.
- **Generic sentence:** "I would welcome a conversation about how my experience could contribute to your team." *(generic closing statement)*

The same review also shows the reviewer's main weakness: it listed "no explicit mention of SQL" as a gap, although the CV lists SQL (see [Known limitations](#known-limitations)).

**Does it generalise?** On three made-up non-AI ads (bartender, nurse, accountant), the Job Analyst kept the "never guess" rules and captured all certificates and travel. It did put two "preferred" items (experience and a certificate) where they read as required. Details are in [docs/model-comparison-job-analyst.md](docs/model-comparison-job-analyst.md#does-it-generalise-non-ai-job-ads-2026-10-22).

## Key design decisions

The full list with reasons is in [docs/decisions.md](docs/decisions.md). The most important ones:

- **Fixed routing instead of an AI router.** The flow is always the same four steps, so a model deciding the order would only add a way to fail.
- **The pipeline is a list of steps.** Each step says which agent to call, what to send and what to save; adding an agent means adding one step. See decision 3 in [docs/decisions.md](docs/decisions.md).
- **Local by default, cloud optional, behind one model client.** Nothing is paid and nothing leaves the machine unless you choose a Claude model. The provider is chosen in one place, and the prompts stay the same. See decision 5 in [docs/decisions.md](docs/decisions.md).
- **The model belongs to the agent.** Each agent picks its model at startup and reports it in its result metadata. The orchestrator records it but never chooses it.
- **Model chosen by measurement, not by feel.** Three local models were scored on seven real job ads with a fixed scorecard; `ministral-3:8b` made the fewest mistakes that matter. See [docs/model-comparison-job-analyst.md](docs/model-comparison-job-analyst.md).
- **The model does the reading, plain Python does everything that must be exact:**
  - removing duplicates and moving "a plus" items to preferred;
  - checking that every quote really appears in the CV;
  - the match score and the summary text.
- **Paused state lives in the A2A task.** When the CV Matcher asks questions, it saves its half-finished analysis in the task's metadata. The follow-up message with the same task id continues from there.

## What I learned

- **A2A basics in practice:**
  - an agent card describes what an agent *can* do;
  - a task carries the status of *one* request;
  - `input-required` lets an agent pause and continue the same task later.
- **The A2A Python SDK 1.x is very different from 0.3.** It's built on protobuf, which shows up in small ways: numbers come back as floats, and status values are named like `TASK_STATE_COMPLETED`. Reading the installed source was more reliable than examples online.
- **A JSON schema guarantees the shape, not the quality.** Small models still guess facts, mix up required and preferred, and copy long sentences. Prompt rules, a worked example, temperature 0 and a plain-Python clean-up each fixed part of it.
- **Measure before you choose.** A simple scorecard, run on the same ads for every model and prompt version, turned "this feels better" into numbers.
- **Ground the model's claims.** Asking for an exact quote, and then checking it in code, catches invented proof. It does not catch weak proof, though; that is still on the backlog.
- **Version everything you compare.** Results record the agent version and the prompt file used. A prompt change applies right away, but a code change only after a restart, and that difference once produced a misleading test run.
- **"Same schema" across providers isn't free.**
  - Adding Claude needed one module and a startup check.
  - But the API enforces the JSON shape, not array lengths, and no longer takes a temperature, so those differences had to be handled and written down.
  - Re-running the local model after the change and getting identical output was the proof that nothing else moved.

## Known limitations

See [docs/backlog.md](docs/backlog.md) for the full list with possible fixes. The main ones:

- **Weak proof:** a quote can be real but still not prove the requirement.
- **Split alternatives:** the Job Analyst turns "such as A, B or C" into separate required items.
- **Lost pauses:** paused tasks are lost when an agent restarts, because the task store is in memory.
- **Narrow testing:** the prompts were tuned on 7 senior AI job ads in English, plus a small check on 3 made-up non-AI ads.
- **Reviewer false positives and shifting verdicts:** the reviewer sometimes flags a true statement (e.g. "no SQL" when the CV lists SQL), or a stated wish as an overclaim. It doesn't know today's date, so it can miscount years "until today". With Haiku, the verdict for the same application can change between runs. Its findings are a second opinion, not facts.
- **Same model family reviewing itself (with Haiku):**
  - With `--preset haiku`, the Application Reviewer is the same model family as the agents whose work it reviews, so it may share their blind spots. Locally it is a different model on purpose.
  - The grounding checks in plain Python (every quote must exist in the CV or the letter) are the independent layer.
  - **A tiny planted-error test** (one letter, 4 mistakes, 2 runs each):
    - Haiku caught the three factual mistakes (inflated years, a skill not in the CV, a wrong company fact) but not an irrelevant claim;
    - Sonnet caught all four, at about 15 times the cost.
- **Unchecked sentences:** the Cover Letter Writer only checks the claims the model lists itself; a factual sentence that isn't on the list is not checked.
- **Terminal only:** the orchestrator asks its questions in the terminal; there is no web front end yet.
