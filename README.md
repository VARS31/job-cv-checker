# Job Ad & CV Checker

A small multi-agent system that reads a job ad, checks a CV against it, and (soon) writes a cover letter. The agents talk to each other with the **A2A (Agent-to-Agent) protocol** and run entirely on **local models via Ollama**: no paid APIs, no data leaves the machine.

I built it as a learning project for A2A and multi-agent design, so the code is deliberately small and commented at every A2A concept (agent card, task, status, artifact, input-required).

> **Status:** the Job Analyst and CV Matcher work end to end. The **Cover Letter Writer** and the **orchestrator** are still in progress; for now, each agent is tested with its own script.

## What it does

1. **Job Analyst**: reads a job ad and returns its requirements as structured JSON: job title, company, education, years of experience, hard skills (required vs. preferred), soft skills, languages, responsibilities, travel and certifications.
2. **CV Matcher**: takes those requirements plus a CV (PDF) and checks every requirement against the CV:
   - Each item is **found** (with an exact quote from the CV as proof), **missing**, or **unclear**.
   - If required items are unclear, the task **pauses** and asks the user up to 5 yes/no questions (A2A `input-required`). The answers continue the same task.
   - The result is a match score (required items count 2, preferred count 1) and a short report.
3. **Cover Letter Writer** *(in progress)*: will write a cover letter from the job requirements and the match report.

## Architecture

```
                         ┌──────────────────────────────┐
   job ad (text)         │  Orchestrator  (in progress) │
   CV (PDF)  ──────────▶ │  plain Python, fixed routing │
                         └──────┬─────────┬─────────┬───┘
                                │ A2A     │ A2A     │ A2A   (JSON-RPC over HTTP)
                                ▼         ▼         ▼
                  ┌──────────────┐ ┌─────────────┐ ┌──────────────────────┐
                  │ Job Analyst  │ │ CV Matcher  │ │ Cover Letter Writer  │
                  │ :9001        │ │ :9002       │ │ :9003  (in progress) │
                  │ ad → JSON    │ │ JSON + PDF  │ │                      │
                  │ requirements │ │ → score,    │ │                      │
                  │              │ │ + questions │ │                      │
                  └──────┬───────┘ └──────┬──────┘ └──────────┬───────────┘
                         │                │                   │
                         └────────────────┼───────────────────┘
                                          ▼
                              agents/model_client.py   (the only place that calls a model)
                                          ▼
                              Ollama on localhost:11434   (e.g. ministral-3:8b)
```

- **A2A:** each agent is its own HTTP server with a public **agent card** at `/.well-known/agent-card.json`. Requests create **tasks** with a status (`working`, `input-required`, `completed`, `failed`). Results come back as **artifacts** made of **parts** (text, structured data, or files).
- **Local models:** every model call goes through one module, `agents/model_client.py`. It sets the JSON schema, the context size (8192), temperature 0, a timeout, and warns when a request gets close to the context limit.
- **Prompts as files:** each agent's instructions live in `prompts/*.md`, so they can be edited without touching code.

## Project layout

```
agents/
  model_client.py        the only module that talks to Ollama
  job_analyst/           agent 1 (port 9001): __main__.py = server + logic, schema.py = JSON shape + clean-up
  cv_matcher/            agent 2 (port 9002): __main__.py, schema.py (checklist, quote check, questions), scoring.py
prompts/                 agent instructions (Markdown)
scripts/                 test tools until the orchestrator exists
samples/                 put your own job ads (*.txt) and CVs (cvs/*.pdf) here; not committed
results/                 evaluation output; not committed
docs/                    decisions, model comparison, backlog
```

## How to run

**You need:** Python 3.11, [Ollama](https://ollama.com), and about 6 GB of disk space for the model.

```bash
# 1. Get a local model
ollama pull ministral-3:8b

# 2. Set up Python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure: copy the example, then set both models to ministral-3:8b
cp .env.example .env
```

**Job Analyst.** Run each part in its own terminal, with the venv activated:

```bash
python -m agents.job_analyst                                   # terminal 1: agent on :9001
python scripts/send_test_message.py samples/my_job_ad.txt      # terminal 2: one ad
python -m scripts.run_all_samples                              # terminal 2: all ads → results/<model>/
```

**CV Matcher:**

```bash
python -m agents.cv_matcher                                    # terminal 1: agent on :9002
python scripts/test_cv_matcher.py results/ministral-3_8b/my_job_ad.json samples/cvs/my_cv.pdf
```

The test script prints each question, waits for a `y`/`n` answer, sends the answers back to the same task, and prints the final report plus the raw A2A JSON of each step.

You can see an agent card in the browser at http://localhost:9001/.well-known/agent-card.json (or `:9002`).

Set `MODEL_DEBUG=true` in `.env` to save the exact requests sent to the model in `results/<model>/prompts/`.

## Key design decisions

The full list with reasons is in [docs/decisions.md](docs/decisions.md). The most important ones:

- **Fixed routing instead of an AI router.** The flow is always the same three steps, so a model deciding the order would only add a way to fail.
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
- **Not finished:** the Cover Letter Writer and the orchestrator are still in progress.
