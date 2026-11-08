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

### Willingness requirements are marked "missing" instead of asked
- **Problem:** "occasional travel to customers (about 10%)" was marked **missing** by both the local model and Haiku in the demo run, so the candidate was never asked. Willingness (to travel, to work shifts, to be on site) can't be proven by a CV, so it should always be a question.
- **Possible fix:** in plain Python, turn a "missing" required item into "unclear" (so it's asked) when its text matches willingness words (travel, shifts, on-site, relocate), or ask the Job Analyst to mark such items.

### Paused tasks are lost when the agent restarts
- **Problem:** the in-memory task store forgets every task on restart, so answers to a paused task then fail with "task not found".
- **Possible fix:** use the SDK's `DatabaseTaskStore` with SQLite (needs the `a2a-sdk[sqlite]` extra; ask before installing).

## Job Analyst

### "Preferred" on experience and certificates is lost
- **Problem:** on the non-AI ads, "*ideally* 2 years on a surgical ward" became a required `experience_details` item, and "Bilanzbuchhalter IHK *is a plus*" landed in `other_requirements`. Both read as required. The schema only has preferred *skills*, and the clean-up only checks `hard_skills_required`.
- **Possible fix:** add `experience_preferred` and `other_preferred` fields (or a required flag per item), and run the "a plus" clean-up on every required list.
- **Update (2026-11-08):** this is Claude Haiku's main weak spot: 10 wrong-field items on 10 ads, and every one carries a marker such as "(preferred)", "(a plus)" or "(strongly preferred)" inside `experience_details` or `other_requirements`. Running the existing clean-up on those lists would catch all of them. It changes scoring, so it needs a product decision. See [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md).

### "Such as A, B or C" alternatives become separate required items
- **Problem:** "agentic AI frameworks such as LangGraph, CrewAI, AutoGen or OpenAI Agents SDK" becomes four required items, so a CV with one of them loses points for the other three.
- **Possible fix:** a stronger prompt rule plus a worked example, or an "any of" group in the schema that the CV Matcher counts as one item.
- **Update (2026-11-08):** Claude Haiku keeps the frameworks example together as one item, but splits "expertise in at least two of these domains" (ad 6) into 13 separate required skills. An "any of" / "at least N of" group would fix both models.

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

### The Reviewer never sees the ad's company description
- **Problem:** the Reviewer gets only the Job Analyst's fields (title, company, skills, experience, responsibilities), not the ad's "About us" text. In the Haiku demo run, it flagged two true sentences about the company (taken from the candidate's own answer) as overclaims, because "the job data does not mention shipping data or freight companies", which the ad does.
- **Possible fix:** pass the job ad text (or a short company description from the Job Analyst) to the Reviewer, and tell it that sentences from the user's answer are the user's own statements.

### Planted-error test with Sonnet as the Reviewer (planned next)
- **Problem:** with `--preset haiku`, the Reviewer is the same model family as the agents it reviews, so it may share their blind spots. Only the plain-Python grounding checks are independent.
- **Plan:** plant known errors in demo letters (an invented skill, a wrong number of years, a generic sentence) and measure how many each Reviewer finds: local `granite4.1:8b`, Haiku, and Claude Sonnet as an outside reviewer.

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

### Spot-check the model-read Haiku scores
- **Problem:** the Haiku column of the Job Analyst scorecard was drafted by Claude, not hand-scored. The local hand score also reads two placements and one vague item differently from the strict written rule.
- **Next step:** spot-check the listed items in [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md) and settle the strict-vs-hand reading.
