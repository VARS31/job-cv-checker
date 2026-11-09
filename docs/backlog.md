# Backlog: known weak spots

## CV Matcher

### Quotes that exist but don't prove the requirement
- **Problem:** the quote check only proves the words are in the CV, not that they prove the requirement (e.g. "multi-step AI workflow" for "multi-agent orchestration", a degree in an unrelated field for "CS, engineering or related field").
- **Possible fix:** a second, short verification step per match: "Does this quote prove this requirement? yes/no".

### Saved state stays visible in task metadata after completion
- **Problem:** the half-finished analysis (`cv_matcher_state`) stays in `task.metadata` after the task is completed, so every client can still read it.
- **Possible fix:** overwrite the key with an empty value in the final status update, or keep the state outside the task (e.g. in the agent's own store keyed by task id).

### The Cover Letter Writer keeps the full CV text in task metadata
- **Problem:** when the Cover Letter Writer pauses for its question, it saves its inputs, **including the full CV text**, in `task.metadata` (`cover_letter_state`), so that the PDF isn't read twice. Like `cv_matcher_state`, the state stays there after the task is completed, and any client that can read the task can read the CV. This is personal data, so it matters more before any shared or hosted use.
- **Possible fix:** the same as for `cv_matcher_state`: clear the key in the final status update, or keep the state in the agent's own store keyed by task id. Or keep only the PDF's hash and read the PDF again from the follow-up message.

### Items the CV lists plainly are marked "unclear"
- **Problem:** in the demo run, the model marked SQL, PostgreSQL and CI/CD as "unclear" without a quote, although the CV lists all three word for word ("Python, SQL", "FastAPI and PostgreSQL", "GitHub Actions CI/CD"). Evidence rules 8 and 9 (no proof from bare skill lists) probably make it too cautious. A user who answers "no" by mistake turns them into "missing".
- **Possible fix:** before asking, check in plain Python whether the requirement's exact words appear in the CV; if so, use that line as the quote and don't ask.
- **Update (2026-11-08):** with Claude Haiku, the CV Matcher found all three with quotes and asked nothing (see [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md)). The plain-Python check would still help the local model.
- **Update (2026-11-09):** still true locally with the dummy CVs: it asked Jane Doe about RAG and Robin Sample about SQL and PostgreSQL, all stated in their CVs.

### Paused tasks are lost when the agent restarts
- **Problem:** the in-memory task store forgets every task on restart, so answers to a paused task then fail with "task not found".
- **Possible fix:** use the SDK's `DatabaseTaskStore` with SQLite (needs the `a2a-sdk[sqlite]` extra; ask before installing).

## Job Analyst

### "Such as A, B or C" alternatives become separate required items
- **Problem:** "agentic AI frameworks such as LangGraph, CrewAI, AutoGen or OpenAI Agents SDK" becomes four required items, so a CV with one of them loses points for the other three.
- **Possible fix:** a stronger prompt rule plus a worked example, or an "any of" group in the schema that the CV Matcher counts as one item.
- **Update (2026-11-08):** Claude Haiku keeps the frameworks example together as one item, but splits "expertise in at least two of these domains" (ad 6) into 13 separate required skills. An "any of" / "at least N of" group would fix both models.
- **Update (2026-11-09):** after the step 1.1 prompt change, both models split ad 6's domains into separate required skills, and the local model still splits the frameworks.

### Near-duplicates across fields count twice
- **Problem:** the clean-up only removes exact duplicates.
  - In step 1.1, Haiku listed ad 3's six "ways to stand out" items both in `experience_preferred` (as long lines) and in `hard_skills_preferred` (as short names), so they count twice as preferred points.
  - In one demo run it listed "German" and "German language".
- **Possible fix:** a stricter prompt rule ("each fact in exactly one field", with an example), or a plain-Python check that drops a preferred item whose words are all inside another item.

### A requirement is sometimes dropped
- **Problem:** without a temperature, Haiku's output differs between runs. In one of five demo runs it didn't list the travel requirement at all, so the candidate was never asked. The local model dropped the bartender's "availability on Friday and Saturday nights" after the step 1.1 prompt change.
- **Possible fix:** none cheap. Missing items aren't on the scorecard yet; a "missed requirements" count would make this visible.

### The local model lists duties as skills more since step 1.1
- **Problem:** the longer prompt shifted `ministral-3:8b`:
  - the nurse ad's duties ("Vital signs monitoring", "Wound care") became required hard skills;
  - ad 6's duties became soft skills;
  - ad 7's experience lines were split into fragments ("assumptions", "dependencies").

  Vague items went from 13 to 15 on the 7 ads and from 2 to 5 on the made-up ads.
- **Possible fix:** a prompt rule plus an example: "Duties from the task list are responsibilities, never skills"; then re-score.

### Prompt tested on few job types
- **Problem:** the prompt and the clean-up were tuned on 7 English ads for senior AI roles and checked on only 3 short made-up non-AI ads (see the "Does it generalise?" section of the model comparison). German markers like "von Vorteil" worked for languages because the model handled them, but they are not in `PREFERRED_MARKER`, and "wünschenswert" or "idealerweise" are untested.
- **Possible fix:** collect a few real ads from other job types and in German, score them with the same scorecard, and add German markers to the prompt and to `PREFERRED_MARKER` in `agents/job_analyst/schema.py`.

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

### Company Research agent for paragraph 3 of the cover letter
- **Problem:** paragraph 3 ("why this company") can only use the user's own answer, so it is often thin.
- **Possible fix:** a fifth A2A agent that fetches the company's website and returns a few facts with their source URL, which the Cover Letter Writer may use like CV quotes.
- **Risks:**
  - **Invented company facts:** the model may summarise wrongly or add facts. Every fact would need an exact quote from the fetched page, checked in plain Python like the CV quotes.
  - **Prompt injection:** a web page can contain hidden text such as "ignore your instructions". Page text must be treated as data, never as instructions, kept short, and never given to an agent that can take actions.

## Cover Letter Writer

### Sentences that are not in the claims list are never checked
- **Problem:** the model writes the claims list itself, and some factual sentences in the letter are not on it (e.g. "defining clear data flows, integration standards and guardrails"), so they are never checked.
- **Possible fix:** a sentence-by-sentence check: split the letter into sentences and require every factual sentence to map to a proven claim; rewrite or flag the ones that don't.

### Paragraph 3 mixes in CV content
- **Problem:** paragraph 3 ("why this company") should use only the user's answer, but the model adds CV skills to it.
- **Possible fix:** write paragraph 3 in a separate model call that only receives the user's answer and the company name, so it cannot use anything else.

## Application Reviewer

### Rank confirmed "no" answers and experience gaps highest
- **Problem:** the reviewer's top 3 weaknesses don't follow a fixed priority, so a missing preferred item can outrank a required one the user explicitly said "no" to.
- **Possible fix:** in the rubric (and checked in plain Python), rank user-confirmed "no" answers and missing required experience (years, experience details) first, then other required gaps, then everything else.

### Reviewer false positives
- **Problem:** the reviewer sometimes flags something true. In the demo run, it listed "no explicit mention of SQL" as a gap although the CV lists SQL, and flagged the candidate's own wish ("I want to build RAG assistants that real customers use") as an overclaim.
- **Possible fix:** require each overclaim to come with a CV quote or report item that **contradicts** the sentence, checked in plain Python like the other quotes. Drop overclaims without a contradiction, and skip sentences that come from the user's own answer.

### The Reviewer doesn't know today's date
- **Problem:** CVs say "09/2019 - today". In one Haiku run the Reviewer counted that as "about six years" (it's seven) and flagged the true "seven years" as an overclaim, because the input has no date.
- **Possible fix:** put today's date into the Reviewer's (and the CV Matcher's) input, in plain Python; or compute years of experience in plain Python.

### Verdicts vary between Haiku runs
- **Problem:** the same strong application (Jane Doe) got shortlist, maybe, shortlist in three Haiku runs, with the same 100% score. One flagged sentence can move the verdict.
- **Possible fix:** give the verdict a plain-Python floor from the report (e.g. no missing required items and no grounded overclaims about requirements → at least "maybe"), or run the Reviewer more than once and report the spread.

### Option: Haiku agents with a Sonnet Reviewer
- **Idea:** in the tiny planted-error test, Sonnet caught all 4 mistakes in both runs, Haiku 3 of 4 (it missed the irrelevant claim). A mixed preset would also take the Reviewer out of the agents' model family.
- **Cost:** about $0.035 per review instead of $0.0024, so roughly $0.04 per run instead of $0.008.
- **Before deciding:** a bigger test than one letter (more letters, more mistake types, the local `granite4.1:8b` too).

### Rewrite loop between reviewer and writer
- **Idea:** the reviewer's overclaims and generic sentences go back to the Cover Letter Writer for a revised letter, for at most 2 rounds. The reviewer itself stays report-only.
- **Risk:** each round costs one or two model calls and can drift away from the proven claims, so the claims check must run again after every rewrite.

## Front end

### Web page with live status (optional)
- **Idea:** one plain HTML page instead of the terminal: upload a CV, paste an ad, answer the questions in the browser, and see each agent's status live.
- **How:** use A2A streaming (`SendStreamingMessage`, server-sent events) so the page receives status updates and artifacts as they happen. The agents currently have `streaming=False` in their cards, so this needs streaming support in the agents and the orchestrator.

## Orchestrator and set-up

### Agent ports are written in four places
- **Problem:** each port lives in the agent's own `PORT` constant, in the `*_URL` settings in `.env` (read only by the orchestrator), in `scripts/start_agents.py`, and in the `AGENT_URL` of each `try_*` script and `run_all_samples.py`. Changing a URL in `.env` doesn't move the agent, it only makes the orchestrator look in the wrong place. (A test checks that the agents, the pipeline and `start_agents.py` agree.)
- **Possible fix:** one settings source for host and port that every agent and script reads, with the defaults in one module.

### Ctrl+C during a run leaves `run_log.json` at "running"
- **Problem:** Ctrl+C is caught in `orchestrator/__main__.py` outside the run, so the run store never writes a final status. The run folder then says `"status": "running"` forever.
- **Possible fix:** catch the interrupt inside `run()`, call `run_store.finish("stopped", "stopped by you")`, then exit.

### Spot-check the model-read scores
- **Problem:** Haiku's step 1 scores and both columns after the step 1.1 fixes were drafted by Claude, not hand-scored. (The strict reading is now applied to both columns.)
- **Next step:** spot-check the listed items in [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md).
