# CLAUDE.md

## Project goal

A "job ad and CV checker" built as a learning project for the A2A protocol and multi-agent systems.

- **4 A2A agents** (ports 9001–9004):
  - **Job Analyst** (9001) – reads a job ad and pulls out the key requirements.
  - **CV Matcher** (9002) – compares the CV to those requirements and asks the user yes/no questions via the A2A `input-required` state.
  - **Cover Letter Writer** (9003) – writes a cover letter from the results.
  - **Application Reviewer** (9004) – reviews the whole application like a recruiter; reports only, never rewrites.
- **Orchestrator:** a Python program with fixed (hard-coded) routing between the agents.
- **Models:** local by default via Ollama (`OLLAMA_URL` in `.env`); Claude Haiku optional per agent (see Constraints). The model belongs to the agent: each agent reads its model at startup and reports it in its result metadata.
- **Later:** one plain HTML page as a simple front end.

## Working mode

- **Decide yourself** on anything small, reversible and inside this repo: naming, file structure, small refactors, test data, prompt wording within my stated rules, code clean-ups. Don't stop to ask. At the end of each task, list them under **"Decisions I made"** so I can review.
- **Ask first only for:**
  - installing new packages;
  - anything irreversible (history rewrites, force pushes, deleting repos or files outside the repo);
  - anything involving personal data or publishing;
  - product decisions that change what the user sees or how scoring works.
- **Big new features** (a new agent, the orchestrator): show the plan briefly, then continue unless something needs one of the "ask first" decisions above.
- Explain every new file in simple words.
- When unsure about a library's API, read the installed package's source code (in `.venv`) instead of guessing from memory.
- The A2A SDK 1.x differs a lot from 0.3: do not rely on 0.3 examples or memory; check the installed version.
- Tests: `python -m pytest` (plain-Python logic only: no models, no network, no personal files). Run them before and after every change.

## Constraints

- Python 3.11.
- Virtual environment in `.venv`.
- **Local by default, cloud optional.** Paid APIs only as an explicit opt-in per agent (a `claude-...` model name, or `scripts/start_agents.py --preset haiku`), never as a silent fallback. Every paid call goes through the budget guard (`agents/budget.py`, limits in `.env`). Never open, print or log `ANTHROPIC_API_KEY`.
- With a Claude model, the job ad and the CV text are sent to Anthropic. Measuring runs (model comparisons) use only the fictional demo CV in `samples/demo/`, never a real CV.
- Agents run on ports 9001–9004.
- All model calls go through one model-client module (`agents/model_client.py`).
