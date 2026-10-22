# CLAUDE.md

## Project goal

A "job ad and CV checker" built as a learning project for the A2A protocol and multi-agent systems.

- **3 A2A agents:**
  - **Job Analyst** – reads a job ad and pulls out the key requirements.
  - **CV Matcher** – compares the CV to those requirements and asks the user yes/no questions via the A2A `input-required` state.
  - **Cover Letter Writer** – writes a cover letter from the results.
- **Orchestrator:** a Python program with fixed (hard-coded) routing between the agents.
- **Models:** local models via Ollama (`http://localhost:11434`).
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

## Constraints

- Python 3.11.
- Virtual environment in `.venv`.
- No paid APIs.
- Agents run on ports 9001–9003.
- All model calls go through one model-client module.
