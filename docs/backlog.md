# Backlog: known weak spots

## CV Matcher

### Quotes that exist but don't prove the requirement
- **Problem:** the quote check only proves the words are in the CV, not that they prove the requirement (e.g. "multi-step AI workflow" for "multi-agent orchestration", a degree in an unrelated field for "CS, engineering or related field").
- **Possible fix:** a second, short verification step per match: "Does this quote prove this requirement? yes/no".

### Saved state stays visible in task metadata after completion
- **Problem:** the half-finished analysis (`cv_matcher_state`) stays in `task.metadata` after the task is completed, so every client can still read it.
- **Possible fix:** overwrite the key with an empty value in the final status update, or keep the state outside the task (e.g. in the agent's own store keyed by task id).

### Paused tasks are lost when the agent restarts
- **Problem:** the in-memory task store forgets every task on restart, so answers to a paused task then fail with "task not found".
- **Possible fix:** use the SDK's `DatabaseTaskStore` with SQLite (needs the `a2a-sdk[sqlite]` extra; ask before installing).

## Job Analyst

### "Such as A, B or C" alternatives become separate required items
- **Problem:** "agentic AI frameworks such as LangGraph, CrewAI, AutoGen or OpenAI Agents SDK" becomes four required items, so a CV with one of them loses points for the other three.
- **Possible fix:** a stronger prompt rule plus a worked example, or an "any of" group in the schema that the CV Matcher counts as one item.

### Prompt tuned on 7 senior AI ads only
- **Problem:** the prompt and the clean-up were only tested on 7 English ads for senior AI and architecture roles. Other job types and German markers like "von Vorteil", "wünschenswert" or "idealerweise" are untested.
- **Possible fix:** add a few ads from other job types and in German to `samples/`, compare the results with the scorecard, and add German markers to the prompt and to `PREFERRED_MARKER` in `agents/job_analyst/schema.py`.

## Ideas

### Priority per requirement from the Job Analyst
- **Problem:** all required items weigh the same (2 points), so a core skill counts as much as a side remark, and question order is set by a fixed rule.
- **Possible fix:** let the Job Analyst return a priority per requirement (e.g. core / normal), and use it for the weights and the question order.

### Prefer recent experience over old
- **Problem:** a skill used 10 years ago counts as much as one used last year.
- **Possible fix:** ask the model for the date range of each quote and give old evidence less weight, or mark it as "older experience" in the report.

### "Add this to your CV" for confirmed items
- **Problem:** items the user confirmed with "yes" but the CV doesn't mention are only listed as "confirmed by you", although a recruiter reading the CV won't see them.
- **Possible fix:** list them in the report as "add this to your CV", ideally with a hint where it fits.
