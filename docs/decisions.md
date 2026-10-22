# Decisions

## 1. Fixed routing instead of model-based routing

The orchestrator calls the agents in a fixed order written in Python, rather than letting a model decide which agent to call next. This keeps the flow predictable and easy to debug while learning A2A.

## 2. Local models via Ollama behind one swappable model client

All model calls go through a single model-client module that talks to Ollama on `localhost:11434`. This keeps the project free of paid APIs and means we can swap the model or provider by changing one file.

## 3. The orchestrator is a fixed list of pipeline steps

The pipeline is always Job Analyst → CV Matcher → Cover Letter Writer, so the order is a plain Python list (`orchestrator/pipeline.py`), not a decision made at run time. Each step is a small object that says:
- which agent it calls (URL from `.env`, plus the command to start it);
- how to build the agent's message from the results so far;
- how to read the agent's artifact into new results;
- which output files to save.

The orchestrator loop itself knows nothing about specific agents. Adding a fourth agent (e.g. an Application Reviewer) means writing one more step and appending it to the list; the loop, the input-required handling and the run saving stay unchanged.

Other choices that follow from this:
- **Fail fast:** all agent cards are read before any work starts. A missing agent costs a second, not a half-finished run.
- **One generic input-required handler:** agents describe their questions in the A2A message itself (a data part with question ids means yes/no, otherwise free text). The orchestrator needs no agent-specific code to answer them. At most 3 rounds per agent, so a confused agent can't loop forever.
- **One context id per run:** every task in a run belongs to the same A2A context. The SDK accepts a new task with a client-chosen context id, and only checks that follow-ups match their task's context.
- **Stop on failure, keep what's done:** each step's outputs and the run log are written as soon as the step finishes, so a failed run still shows how far it got and why.
