# Lessons learned

What building this project taught me, roughly in the order it happened.

## A2A

- **The basics, in practice:**
  - an agent card describes what an agent *can* do;
  - a task carries the status of *one* request;
  - `input-required` lets an agent pause and continue the same task later, with the half-finished work kept in the task.
- **The A2A Python SDK 1.x is very different from 0.3.** It's built on protobuf, which shows up in small ways: numbers come back as floats, and status values are named like `TASK_STATE_COMPLETED`. Reading the installed source was more reliable than examples online.
- **The model belongs to the agent.** Agents are opaque: the orchestrator sees cards and results, not models. Letting each agent report its model, tokens and cost in its result metadata kept that boundary and still made every run accountable.

## Models

- **A JSON schema guarantees the shape, not the quality.** Small models still guess facts, mix up required and preferred, and copy long sentences. Prompt rules, a worked example, temperature 0 and a plain-Python clean-up each fixed part of it.
- **A schema that has no place for something invites mistakes.** With preferred *skills* only, preferred experience and certificates had to land in required fields. Haiku even wrote "(preferred)" into the items. Two new fields fixed it for both models; a prompt rule alone wouldn't have.
- **"Same schema" across providers isn't free.** Adding Claude needed one module and a startup check. But the API enforces the JSON shape, not array lengths, and no longer takes a temperature, so those differences had to be handled and written down. Re-running the local model after the change and getting identical output was the proof that nothing else moved.
- **Without a temperature, runs differ.** With Claude, the same application got different verdicts, and the Job Analyst sometimes left out a requirement. One run is an example, not a result.

## Measuring

- **Measure before you choose.** A simple scorecard, run on the same ads for every model and prompt version, turned "this feels better" into numbers.
- **Write the prediction down first.** The dummy CVs' expected outcomes and the planted errors were committed before any run, so the results could be compared with something fixed.
- **Call a test what it is.** One letter with four mistakes is a tiny test, not an evaluation. Scores drafted by a model are model-read until a person checks them.
- **Version everything you compare.** Results record the agent version and the prompt used. A prompt change applies right away, but a code change only after a restart, and that difference once produced a misleading test run.

## Grounding

- **Ground the model's claims.** Asking for an exact quote, then checking it in code, catches invented proof. It doesn't catch weak proof.
- **A second model as reviewer needs its own inputs.** The Reviewer flagged true company facts as invented until it got the original ad; it miscounted "09/2019 – today" until it got today's date.

## Infrastructure

- **Test what a lock really covers.** The budget guard's `flock` worked between processes on the Mac, but not between Docker containers sharing a folder: a small two-container test showed both getting the lock. An exclusive lock *file* (`O_CREAT|O_EXCL`) works in both places.
- **A trace across processes needs the context passed on.** The A2A SDK makes client and server spans, but without the trace context in the HTTP headers they land in separate traces. And the SDK's internal spans (240 of 319 in the first run) hid the useful ones until they were filtered out.
- **Look at the picture.** The first Phoenix screenshots looked plausible and showed the trace *list*, not the span. Only opening the image showed it.
