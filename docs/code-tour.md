# Code tour

Where things are, what a run saves, and the tools for running one agent at a time.

## Layout

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
  server.py              serving an agent: the A2A routes, tracing, where to listen (the same for all four)
  tracing.py             OpenTelemetry for all five processes (off by default)
  cv_text.py             shared: CV PDF to text, the quote check, today's date
  job_analyst/           agent 1 (port 9001): __main__.py = the agent, schema.py = JSON shape + clean-up
  cv_matcher/            agent 2 (port 9002): __main__.py, schema.py (checklist, questions), scoring.py
  cover_letter_writer/   agent 3 (port 9003): __main__.py, schema.py (claims check, style check)
  application_reviewer/  agent 4 (port 9004): __main__.py, schema.py (rubric schema, grounding, cliché check, review.md)
prompts/                 agent instructions (Markdown); local models and Claude get the same prompts
scripts/
  start_agents.py        all four agents in one terminal (--preset local|haiku|haiku-sonnet)
  docker_up.py           the same in Docker, optionally with the trace viewers
  run_all_samples.py     the Job Analyst on many ads (model comparisons)
  try_*.py               interactive tools for one agent at a time
  make_demo_cv.py        builds the fictional demo CVs
tests/                   pytest: plain-Python logic only (no models, no network, no personal files)
samples/demo/            fictional CVs, job ads, scripted answers, expected outcomes, the planted-error test
samples/, results/       your own job ads and CVs, and every run's output: not committed
Dockerfile, docker-compose.yml, .dockerignore   the optional Docker set-up
```

Agent versions: Job Analyst 0.6.0, CV Matcher 0.4.0, Cover Letter Writer 0.3.0, Application Reviewer 0.3.0.

## What a run saves

`python -m orchestrator <ad> <cv>` saves everything in `results/runs/<date-time>/`:
- `requirements.json` and `match_report.json`;
- `cover_letter.md`, and `claims.json` with the checked claims and style warnings;
- `review.md` and `review.json` from the Application Reviewer;
- `job_ad.txt`, a copy of the ad, so the run can be reviewed again later;
- `run_log.json`:
  - per step: the task id, final state, model, tokens, cost, seconds, and every question asked with its answer;
  - the totals for the run, and the trace id when tracing is on.

**Repeatable runs:** `--answers FILE` takes the answers from a JSON file instead of the terminal. Questions are matched by the words they contain, not by their ids, so two set-ups get the same answers even when their models word the questions differently. Format: `orchestrator/answers.py`; examples: `samples/demo/answers_*.json`.

## One agent at a time

```bash
python -m agents.job_analyst                                   # terminal 1: agent on :9001
python scripts/try_job_analyst.py samples/my_job_ad.txt        # terminal 2: one ad
python -m scripts.run_all_samples                              # all ads in samples/ → results/<model>/
python -m scripts.run_all_samples samples/demo/*.txt --out results/compare   # chosen ads, another folder

python -m agents.cv_matcher                                    # agent on :9002
python scripts/try_cv_matcher.py results/ministral-3_8b/my_job_ad.json samples/cvs/my_cv.pdf

python -m agents.cover_letter_writer                           # agent on :9003
python scripts/try_cover_letter.py results/ministral-3_8b/my_job_ad.json results/cv_matcher/my_job_ad__my_cv.json samples/cvs/my_cv.pdf

python -m agents.application_reviewer                          # agent on :9004
python -m scripts.try_reviewer results/runs/<date-time>        # review a run again (--letter: another letter)
```

- **The `try_*` scripts are interactive tools, not tests:** they print the raw A2A JSON of each step.
- **Agent cards:** each card is visible in a browser at <http://localhost:9001/.well-known/agent-card.json> (or `:9002`, `:9003`, `:9004`).
- **Debugging prompts:** `MODEL_DEBUG=true` in `.env` saves the exact requests sent to a local model in `results/<model>/prompts/`.
