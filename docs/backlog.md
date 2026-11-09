# Backlog

One list of known weak spots and ideas, roughly in pipeline order. Each item says the problem and a possible fix. Items that were fixed have been removed; how they were fixed is in [decisions.md](decisions.md).

1. **[Job Analyst] "Such as A, B or C" alternatives become separate required items.**
   - **Problem:** "agentic AI frameworks such as LangGraph, CrewAI, AutoGen or OpenAI Agents SDK" becomes four required items, so a CV with one of them loses points for the other three. Haiku keeps that example together but splits "expertise in at least two of these domains" (ad 6) into separate required skills; since step 1.1 the local model does too.
   - **Fix:** a stronger prompt rule plus a worked example, or an "any of" / "at least N of" group in the schema that the CV Matcher counts as one item.

2. **[Job Analyst] Near-duplicates across fields count twice.**
   - **Problem:** the clean-up only removes exact duplicates. In step 1.1, Haiku listed ad 3's six "ways to stand out" items both in `experience_preferred` (as long lines) and in `hard_skills_preferred` (as short names), so they count twice as preferred points. In one demo run it listed "German" and "German language".
   - **Fix:** a stricter prompt rule ("each fact in exactly one field", with an example), or a plain-Python check that drops a preferred item whose words are all inside another item.

3. **[Job Analyst] A requirement is sometimes dropped.**
   - **Problem:** without a temperature, Haiku's output differs between runs. In 2 of 11 Haiku runs on the demo ad, it didn't list the travel requirement at all, so the candidate was never asked. The local model dropped the bartender's "availability on Friday and Saturday nights" after the step 1.1 prompt change.
   - **Fix:** none cheap. Missing items aren't on the scorecard yet; a "missed requirements" count would make this visible.

4. **[Job Analyst] The local model lists duties as skills more since step 1.1.**
   - **Problem:** the longer prompt shifted `ministral-3:8b`: the nurse ad's duties ("Vital signs monitoring", "Wound care") became required hard skills, ad 6's duties became soft skills, and ad 7's experience lines were split into fragments ("assumptions", "dependencies"). Vague items went from 13 to 15 on the 7 ads and from 2 to 5 on the made-up ads.
   - **Fix:** a prompt rule plus an example ("Duties from the task list are responsibilities, never skills"), then re-score.

5. **[Job Analyst] The prompt was tested on few job types.**
   - **Problem:** the prompt and the clean-up were tuned on 7 English ads for senior AI roles and checked on only 3 short made-up non-AI ads. German markers like "von Vorteil" worked for languages because the model handled them, but they are not in `PREFERRED_MARKER`, and "wünschenswert" or "idealerweise" are untested.
   - **Fix:** collect a few real ads from other job types and in German, score them with the same scorecard, and add German markers to the prompt and to `PREFERRED_MARKER` in `agents/job_analyst/schema.py`.

6. **[CV Matcher] Quotes that exist but don't prove the requirement.**
   - **Problem:** the quote check only proves the words are in the CV, not that they prove the requirement (e.g. "multi-step AI workflow" for "multi-agent orchestration", or a degree in an unrelated field for "CS, engineering or related field").
   - **Fix:** a second, short verification step per match: "Does this quote prove this requirement? yes/no".

7. **[CV Matcher] Items the CV lists plainly are marked "unclear" (local model).**
   - **Problem:** the local model marks skills that the CV lists word for word as "unclear" and asks about them, e.g. Jane Doe about RAG, Robin Sample about SQL and PostgreSQL. Evidence rules 8 and 9 (no proof from bare skill lists) probably make it too cautious. A user who answers "no" by mistake turns them into "missing". Haiku finds them with quotes.
   - **Fix:** before asking, check in plain Python whether the requirement's exact words appear in the CV; if so, use that line as the quote and don't ask.

8. **[CV Matcher, Cover Letter Writer] Saved state stays visible in task metadata, including the CV text.**
   - **Problem:** paused tasks keep their state in `task.metadata` after they complete. For the CV Matcher (`cv_matcher_state`) that's the half-finished analysis. For the Cover Letter Writer (`cover_letter_state`) it includes **the full CV text**. Any client that can read the task can read it. This is personal data, so it matters before any shared or hosted use.
   - **Fix:** clear the key in the final status update, or keep the state in the agent's own store keyed by task id. For the letter, keeping only the PDF's hash and reading the PDF again from the follow-up message would also work.

9. **[All agents] Paused tasks are lost when an agent restarts.**
   - **Problem:** the in-memory task store forgets every task on restart, so answers to a paused task then fail with "task not found".
   - **Fix:** the SDK's `DatabaseTaskStore` with SQLite (needs the `a2a-sdk[sqlite]` extra; ask before installing).

10. **[Cover Letter Writer] Sentences that are not in the claims list are never checked.**
    - **Problem:** the model writes the claims list itself, and some factual sentences in the letter are not on it (e.g. "defining clear data flows, integration standards and guardrails"), so they are never checked.
    - **Fix:** a sentence-by-sentence check: split the letter into sentences and require every factual sentence to map to a proven claim; rewrite or flag the ones that don't.

11. **[Cover Letter Writer] Paragraph 3 mixes in CV content.**
    - **Problem:** paragraph 3 ("why this company") should use only the user's answer, but the model adds CV skills to it.
    - **Fix:** write paragraph 3 in a separate model call that only receives the user's answer and the company name.

12. **[Reviewer] False positives.**
    - **Problem:** the reviewer sometimes flags something true, e.g. "no explicit mention of SQL" although the CV lists SQL, or the candidate's own stated wish as an overclaim.
    - **Fix:** require each overclaim to come with a CV quote or report item that **contradicts** the sentence, checked in plain Python like the other quotes. Drop overclaims without a contradiction, and skip sentences that come from the user's own answer.

13. **[Reviewer] Verdicts vary between Haiku runs.**
    - **Problem:** the same strong application (Jane Doe) got shortlist, maybe, shortlist in three Haiku runs, with the same 100% score. One flagged sentence can move the verdict.
    - **Fix:** give the verdict a plain-Python floor from the report (e.g. no missing required items and no grounded overclaims about requirements → at least "maybe"), or run the Reviewer more than once and report the spread.

14. **[Reviewer] Rank confirmed "no" answers and experience gaps highest.**
    - **Problem:** the top 3 weaknesses don't follow a fixed priority, so a missing preferred item can outrank a required one the user explicitly said "no" to.
    - **Fix:** in the rubric, and checked in plain Python, rank user-confirmed "no" answers and missing required experience first, then other required gaps, then everything else.

15. **[Reviewer] A bigger Reviewer test.**
    - **Problem:** the planted-error test that led to the `haiku-sonnet` preset was tiny: one letter, four mistakes, two runs per model, and the local `granite4.1:8b` wasn't in it.
    - **Fix:** more letters and mistake types, all three reviewers (local, Haiku, Sonnet), with the mistakes listed before the runs as before.

16. **[Idea] Priority per requirement from the Job Analyst.**
    - **Problem:** all required items weigh the same (2 points), so a core skill counts as much as a side remark, and the question order is set by a fixed rule.
    - **Fix:** let the Job Analyst return a priority per requirement (e.g. core / normal), and use it for the weights and the question order.

17. **[Idea] Prefer recent experience over old.**
    - **Problem:** a skill used 10 years ago counts as much as one used last year.
    - **Fix:** ask the model for the date range of each quote and give old evidence less weight, or mark it as "older experience" in the report.

18. **[Idea] "Add this to your CV" for confirmed items.**
    - **Problem:** items the user confirmed with "yes" but the CV doesn't mention are only listed as "confirmed by you", although a recruiter reading the CV won't see them.
    - **Fix:** list them in the report as "add this to your CV", ideally with a hint where it fits.

19. **[Idea] A Company Research agent for paragraph 3 of the letter.**
    - **Problem:** paragraph 3 ("why this company") can only use the user's own answer, so it is often thin.
    - **Fix:** a fifth A2A agent that fetches the company's website and returns a few facts with their source URL, which the Cover Letter Writer may use like CV quotes.
    - **Risks:** invented company facts (so every fact needs an exact quote from the fetched page, checked in plain Python), and prompt injection (page text is data, never instructions, kept short, and never given to an agent that can take actions).

20. **[Idea] A rewrite loop between the Reviewer and the Writer.**
    - **Problem:** the Reviewer's findings don't change the letter.
    - **Fix:** send its overclaims and generic sentences back to the Cover Letter Writer for at most 2 rounds; the Reviewer stays report-only. Risk: each round costs model calls and can drift from the proven claims, so the claims check must run again after every rewrite.

21. **[Front end] A web page with live status (optional).**
    - **Problem:** everything happens in the terminal.
    - **Fix:** one plain HTML page: upload a CV, paste an ad, answer the questions in the browser, and see each agent's status live through A2A streaming (`SendStreamingMessage`). The agents have `streaming=False` in their cards today, so this needs streaming in the agents and the orchestrator.

22. **[Set-up] Agent ports are written in five places.**
    - **Problem:** each port lives in the agent's `PORT` constant, in the `*_URL` settings in `.env` (read only by the orchestrator), in `scripts/start_agents.py`, in `docker-compose.yml`, and in the `AGENT_URL` of each `try_*` script and `run_all_samples.py`. Changing a URL in `.env` doesn't move the agent. A test checks that the agents, the pipeline and `start_agents.py` agree.
    - **Fix:** one settings source for host and port that every agent and script reads.

23. **[Set-up] Ctrl+C during a run leaves `run_log.json` at "running".**
    - **Problem:** Ctrl+C is caught in `orchestrator/__main__.py` outside the run, so the run store never writes a final status.
    - **Fix:** catch the interrupt inside `run()`, call `run_store.finish("stopped", "stopped by you")`, then exit.

24. **[Set-up] Containers run as root.**
    - **Problem:** the agent image has no user of its own. They listen on 127.0.0.1 only and nothing private is in the image, so this is acceptable for a learning project.
    - **Fix:** add a non-root user in the Dockerfile and check that it can still write the shared spend file in `results/`.

25. **[Evaluation] Spot-check the model-read scores.**
    - **Problem:** Haiku's step 1 scores, and both columns after the step 1.1 fixes, were drafted by Claude, not hand-scored.
    - **Fix:** spot-check the listed items in [comparison-local-vs-haiku.md](comparison-local-vs-haiku.md).
