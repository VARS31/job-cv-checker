# Job Ad & CV Checker

A small multi-agent system that reads a job ad, checks a CV against it, writes an honest cover letter, and reviews the whole application like a recruiter would. The agents talk to each other with the **A2A (Agent-to-Agent) protocol** and run entirely on **local models via Ollama**: no paid APIs, no data leaves the machine.

I built it as a learning project for A2A and multi-agent design, so the code is deliberately small and commented at every A2A concept (agent card, task, status, artifact, input-required).

> **Status:** all four agents and the orchestrator work end to end with one command. Ideas for what comes next are in [docs/backlog.md](docs/backlog.md).

## What it does

1. **Job Analyst**: reads a job ad and returns its requirements as structured JSON: job title, company, education, years of experience, hard skills (required vs. preferred), soft skills, languages, responsibilities, travel and certifications.
2. **CV Matcher**: takes those requirements plus a CV (PDF) and checks every requirement against the CV:
   - Each item is **found** (with an exact quote from the CV as proof), **missing**, or **unclear**.
   - If required items are unclear, the task **pauses** and asks the user up to 5 yes/no questions (A2A `input-required`). The answers continue the same task.
   - The result is a match score (required items count 2, preferred count 1) and a short report.
3. **Cover Letter Writer**: asks the user one free-text question ("why this role?"), then writes a three-paragraph letter from the matched and confirmed items only:
   - Every factual claim must come with an exact quote from the CV or from the user's answer, checked in plain Python. Unproven claims trigger one rewrite.
   - A plain-Python style check fixes dashes and warns about buzzwords, length and structure.
4. **Application Reviewer**: acts as a senior recruiter for the job (a different model, `granite4.1:8b`, at temperature 0) and only reports, never rewrites:
   - a verdict (shortlist / maybe / reject) with a one-sentence reason, the top 3 weaknesses, overclaims and generic sentences in the letter, whether paragraph 3 is company-specific, and 3 to 5 likely interview questions;
   - every quoted letter sentence is checked in plain Python against the letter, and items that don't match are dropped and counted. A plain-Python list of known clichés backs up the model.
5. **Orchestrator**: runs all four in a fixed order with one command, answers the agents' questions through the terminal, and saves the whole run.

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
                           ▼
               Ollama on localhost:11434   (ministral-3:8b, granite4.1:8b)
```

- **A2A:** each agent is its own HTTP server with a public **agent card** at `/.well-known/agent-card.json`. Requests create **tasks** with a status (`working`, `input-required`, `completed`, `failed`). Results come back as **artifacts** made of **parts** (text, structured data, or files).
- **Orchestrator:** reads all agent cards first and stops with a clear message if one isn't running. Each step passes the earlier artifacts on to the next agent. One generic handler answers every agent's `input-required` pause: y/n for questions with ids, free text otherwise.
- **Local models:** every model call goes through one module, `agents/model_client.py`. It sets the JSON schema, the context size (8192), the temperature, a timeout, and warns when a request gets close to the context limit.
- **Prompts as files:** each agent's instructions live in `prompts/*.md`, so they can be edited without touching code.

## Project layout

```
orchestrator/
  __main__.py            one command for the whole pipeline
  pipeline.py            the fixed list of steps (add an agent = add one step)
  agent_runner.py        agent cards, sending messages, the generic input-required handler
  run_store.py           saves each run to results/runs/<date-time>/
agents/
  model_client.py        the only module that talks to Ollama
  cv_text.py             shared: CV PDF to text, and the quote check
  job_analyst/           agent 1 (port 9001): __main__.py = server + logic, schema.py = JSON shape + clean-up
  cv_matcher/            agent 2 (port 9002): __main__.py, schema.py (checklist, questions), scoring.py
  cover_letter_writer/   agent 3 (port 9003): __main__.py, schema.py (claims check, style check)
  application_reviewer/  agent 4 (port 9004): __main__.py, schema.py (rubric schema, grounding, cliché check, review.md)
prompts/                 agent instructions (Markdown)
scripts/                 start_agents.py, plus test tools for single agents
samples/                 put your own job ads (*.txt) and CVs (cvs/*.pdf) here; not committed
results/                 runs and evaluation output; not committed
docs/                    decisions, model comparison, backlog
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

# 3. Configure (models and agent URLs)
cp .env.example .env
```

**The whole pipeline.** Use two terminals, both with the venv activated:

```bash
python scripts/start_agents.py                                   # terminal 1: starts all four agents; Ctrl+C stops them
python -m orchestrator samples/my_job_ad.txt samples/cvs/my_cv.pdf   # terminal 2: the pipeline
```

The orchestrator prints one progress line per agent, asks the CV Matcher's yes/no questions and the Cover Letter Writer's question in the terminal, and saves everything in `results/runs/<date-time>/`:
- `requirements.json`, `match_report.json`;
- `cover_letter.md`, and `claims.json` with the checked claims and style warnings;
- `review.md` and `review.json` from the Application Reviewer;
- `run_log.json` with task ids, final states and seconds per agent.

**Single agents** (for testing one agent at a time):

```bash
python -m agents.job_analyst                                   # terminal 1: agent on :9001
python scripts/send_test_message.py samples/my_job_ad.txt      # terminal 2: one ad
python -m scripts.run_all_samples                              # terminal 2: all ads → results/<model>/

python -m agents.cv_matcher                                    # agent on :9002
python scripts/test_cv_matcher.py results/ministral-3_8b/my_job_ad.json samples/cvs/my_cv.pdf

python -m agents.cover_letter_writer                           # agent on :9003
python scripts/test_cover_letter.py results/ministral-3_8b/my_job_ad.json results/cv_matcher/my_job_ad__my_cv.json samples/cvs/my_cv.pdf

python -m agents.application_reviewer                          # agent on :9004
python scripts/test_reviewer.py results/runs/<date-time>       # review an existing run again
```

These test scripts print the raw A2A JSON of each step. You can see an agent card in the browser at http://localhost:9001/.well-known/agent-card.json (or `:9002`, `:9003`, `:9004`).

Set `MODEL_DEBUG=true` in `.env` to save the exact requests sent to the model in `results/<model>/prompts/`.

## Key design decisions

The full list with reasons is in [docs/decisions.md](docs/decisions.md). The most important ones:

- **Fixed routing instead of an AI router.** The flow is always the same four steps, so a model deciding the order would only add a way to fail.
- **The pipeline is a list of steps.** Each step says which agent to call, what to send and what to save; adding an agent means adding one step. See decision 3 in [docs/decisions.md](docs/decisions.md).
- **Local models behind one model client.** There are no paid APIs, and the model or provider can be swapped in one place.
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

## Known limitations

See [docs/backlog.md](docs/backlog.md) for the full list with possible fixes. The main ones:

- **Weak proof:** a quote can be real but still not prove the requirement.
- **Split alternatives:** the Job Analyst turns "such as A, B or C" into separate required items.
- **Lost pauses:** paused tasks are lost when an agent restarts, because the task store is in memory.
- **Narrow testing:** the prompts were tuned on a small set of senior AI job ads in English.
- **Unchecked sentences:** the Cover Letter Writer only checks the claims the model lists itself; a factual sentence that isn't on the list is not checked.
- **Terminal only:** the orchestrator asks its questions in the terminal; there is no web front end yet.
