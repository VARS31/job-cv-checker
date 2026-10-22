# Model comparison: Job Analyst (2026-10-22)

Three local models, same prompt (`prompts/job_analyst.md`, identical copy in each results folder), same 7 job ads in `samples/`, agent version 0.3.0, temperature 0. Every run finished with `TASK_STATE_COMPLETED`.

- `llama3.2:3b` → `results/llama3.2_3b/`
- `granite4.1:8b` → `results/granite4.1_8b/`
- `ministral-3:8b` → `results/ministral-3_8b/`

## Summary

| Scorecard | llama3.2:3b | granite4.1:8b | ministral-3:8b |
|---|---|---|---|
| Seniority guessed without a signal (ads with no signal: 6) | **6 of 6** | 1 of 6 | 1 of 6 |
| "Or equivalent experience" rule followed (applies to 3 ads) | 2 of 3 | **3 of 3** | **3 of 3** |
| Required vs preferred: items in the wrong field | 8 | 8 | **1** |
| Travel and certifications captured (3 items in 2 ads) | 0 of 3 | 2 of 3 | **3 of 3** |
| Vague items or full sentences | 18 | 42 | **12** |
| Invented facts | 2 | **0** | 2 |
| Seconds, total for 7 ads (average per ad) | **57.9 (8.3)** | 156.0 (22.3) | 153.8 (22.0) |

Bold = best in the row.

## Per ad (llama / granite / ministral)

| Ad | Seniority guessed | Or-equivalent rule | Wrong field | Travel / certs | Vague / sentences | Invented | Seconds |
|---|---|---|---|---|---|---|---|
| 1 BMW | yes / yes / no | n/a | 4 / 0 / 0 | n/a | 1 / 2 / 0 | 0 / 0 / 0 | 8.8 / 21.4 / 23.0 |
| 2 Google | yes / no / no | yes / yes / yes | 1 / 1 / 0 | n/a | 5 / 6 / 0 | 0 / 0 / 0 | 5.9 / 19.5 / 17.0 |
| 3 NVIDIA | yes / no / yes | yes / yes / yes | 0 / 6 / 0 | n/a | 1 / 5 / 2 | 0 / 0 / 1 | 11.3 / 25.8 / 27.9 |
| 4 Mistral | yes / no / no | n/a | 0 / 0 / 1 | travel: no / yes / yes | 0 / 7 / 1 | 1 / 0 / 1 | 6.2 / 18.6 / 17.3 |
| 5 Parloa | no / no / no (has "Sr") | n/a | 0 / 0 / 0 | n/a | 0 / 2 / 2 | 0 / 0 / 0 | 7.1 / 22.2 / 20.5 |
| 6 Alibaba | yes / no / no | n/a | 3 / 1 / 0 | n/a | 3 / 13 / 5 | 1 / 0 / 0 | 9.0 / 21.2 / 21.9 |
| 7 NTT DATA | yes / no / no | no / yes / yes | 0 / 0 / 0 | travel + certs: none / travel only / both | 8 / 7 / 2 | 0 / 0 / 0 | 9.6 / 27.3 / 26.2 |

### Mistakes behind the numbers

- **llama3.2:3b**
  - Wrong field: ad 1 puts AWS or Azure, CI/CD and MLOps under preferred, and leaves "ideally master's or PhD" inside `education_required`. Ad 2 marks German as required (the ad lists it as preferred). Ad 6 puts AutoML, generative AI and model training under preferred, although they are part of the required "at least two of these domains".
  - Invented: "Bachelor's" (ad 4 only says "a degree") and "executive presence" (ad 6).
  - Vague: ad 2 preferred skills like "technical stakeholders" and "executive leaders"; ad 7 "cloud", "data", "integration"; long copied responsibilities in ads 6 and 7.
- **granite4.1:8b**
  - Wrong field: ad 3 puts six "ways to stand out" products (Nemotron, NeMo, AI-Q, OpenShell, NemoClaw, NVIDIA AI Enterprise) under required. Ad 2 marks German as required. Ad 6 puts AWS and Azure under preferred.
  - Vague: ad 6 fills `soft_skills` with 9 duties copied from the responsibilities ("Technical discovery sessions", "Gathering field feedback"). Many responsibilities and experience points are copied sentences of 11–18 words (ads 2, 3, 4, 7).
  - Certifications missed in ad 7.
- **ministral-3:8b**
  - Wrong field: ad 4 puts MEDDPICC under required, with "(preferred)" written inside the item.
  - Invented: "English, required" in ads 3 and 4. Neither ad mentions English.
  - Vague: ad 6 still puts 4 duties into `soft_skills`; a few lumped items ("CRMs, ERPs, contact center platforms, ticketing systems").

### Other things noticed (not on the scorecard)

- **Company in ad 6:** only ministral found "Alibaba Cloud". llama and granite said `not_stated`.
- **Missed preferred skills:** granite dropped prompt engineering and conversation design in ad 5, although the ad calls them a plus.
- **Responsibilities:** llama returned none for ad 1, although the ad lists them. ministral's are consistently short (the prompt asks for ~8 words), and granite's are often full sentences.
- **Duplicates in different wording:** the clean-up only removes exact duplicates, so granite's "communicating in German fluently" (soft skill) and "Chinese language skills" (hard skill) stay next to the `languages` entries.

## Worst single mistake per model

- **llama3.2:3b:** in the BMW ad it moved three required skills (AWS or Azure, CI/CD, MLOps) to "preferred". The CV Matcher would treat must-haves as optional and overrate the match. Close second: it guessed the seniority in every ad without a signal.
- **granite4.1:8b:** in the NVIDIA ad it turned six "stand out" products into required skills. The CV Matcher would report six missing must-haves that are really just a bonus, and underrate the match.
- **ministral-3:8b:** in the Mistral ad it put MEDDPICC (a sales method the ad calls "a plus") into required skills. It's one item, but it is the same kind of error as above.

## Recommendation

**Use `ministral-3:8b` for the Job Analyst.**

In simple words: it makes the fewest mistakes that matter for the next agent.
- It almost always puts required and preferred skills in the right place (1 error, against 8 for the others). That is the most important point, because the CV Matcher scores against exactly these two lists.
- It is the only model that caught travel and certifications every time.
- It keeps items short.
- It follows the "or equivalent experience" rule.

**What you give up:**
- **Speed:** about 22 seconds per ad instead of 8. For one person checking one ad at a time, that is fine.
- **Two invented facts:** it assumed English is required in two ads that don't say so. That is the next thing to fix in the prompt.

**Why not the other two:**
- **llama3.2:3b** is fast, but it guesses seniority in every ad and often mixes up required and preferred skills. Fast wrong answers are not useful for matching.
- **granite4.1:8b** never invented facts, but it copies long sentences, fills `soft_skills` with duties, and made the single most harmful mistake (six bonus products marked as required).

## Limits of this comparison

- **One reviewer scored it:** I scored all 21 results by hand using the rules below. Some calls are judgment ("is this item vague?"), so treat small differences (e.g. 12 vs 18) as rough, and large ones (1 vs 8, 12 vs 42) as real.
- **Small sample:** 7 ads, all for similar senior AI/architecture roles. Results may differ for other job types.
- **Speed includes model loading:** the first ad of each run includes load time, but the effect on the totals is small.

### Scoring rules used

- **Seniority guessed:** a value other than `not_stated` when the ad's wording gives no seniority. Only ad 5 ("Sr") has a signal.
- **Or-equivalent rule:** `education_required` keeps the "or equivalent experience" wording (ads 2, 3, 7).
- **Wrong field:** a required item placed under preferred, or the reverse, including languages and the education fields. Missing items are not counted.
- **Travel / certifications:** travel in ads 4 and 7, certifications in ad 7, captured anywhere in the output.
- **Vague item or full sentence:**
  - a list item over 10 words copied from the ad;
  - a fragment that is not a usable skill ("technical stakeholders", "cloud");
  - a duty listed as a skill;
  - several separate skills squeezed into one item.

  "X or Y" alternatives are not counted, because the prompt asks to keep them together.
- **Invented fact:** a stated fact that is not in the ad. Seniority guesses are counted separately.

---

## v2: ministral-3:8b after two fixes (2026-10-22)

**What changed since v1:**
1. **Prompt rule 8:** only list languages the ad explicitly mentions; the language the ad is written in doesn't count.
2. **Clean-up code (agent 0.4.0):** an item in `hard_skills_required` containing "(preferred)", "a plus", "nice to have" or "ideally" moves to `hard_skills_preferred`, and the marker is removed.

**The run:** all 7 result files say `agent_version: 0.4.0`, so both fixes were active. The prompt copy in `results/ministral-3_8b/job_analyst.md` contains rule 8.

Folders compared: `results/ministral-3_8b_prompt_v1/` (v1) and `results/ministral-3_8b/` (v2).

| Scorecard | v1 | v2 |
|---|---|---|
| Seniority guessed without a signal | 1 of 6 | **0 of 6** |
| "Or equivalent experience" rule followed | 3 of 3 | 3 of 3 |
| Required vs preferred: items in the wrong field | 1 | 1 |
| Travel and certifications captured | 3 of 3 | 3 of 3 |
| Vague items or full sentences | 12 | 12 |
| Invented facts | 2 | **0** |
| Seconds, total (average per ad) | 153.8 (22.0) | 153.6 (21.9) |

**Check of the clean-up, before this run:** an earlier run had the new prompt but the old code (the agent hadn't been restarted, so files said `0.3.0`). I ran the new `clean_requirements()` over those saved results, without changing any files. The prediction was that the clean-up would change exactly one item, MEDDPICC in ad 4.

The real 0.4.0 run matches that prediction item for item. The model's answers were identical in both runs, as expected at temperature 0, and the clean-up changed only MEDDPICC.

The in-between run also showed that **the clean-up matters**. Without it, MEDDPICC stayed under required, so the wrong-field count was 2, not 1.

**What improved:**
- **Languages (the target of fix 1):** ads 3 and 4 no longer list "English, required". Invented facts went from 2 to 0.
- **MEDDPICC (the target of fix 2):** in ad 4 the model still wrote "MEDDPICC or similar sales qualification frameworks (preferred)" under required. The clean-up moved it to preferred and removed "(preferred)". This was the only item the clean-up changed in all 7 ads.
- **Seniority, as a side effect:** ad 3 now says `not_stated` instead of a guessed "senior". The prompt change was about languages, so this is a lucky side effect, not a reliable fix.

**What got worse or stayed the same:**
- **New wrong-field item:** ad 4 now captures "value-based selling" (which v1 had dropped). But it put it under `other_requirements` instead of `hard_skills_preferred`. The ad calls it "a plus", and `other_requirements` reads as required. So the wrong-field count is still 1, but it is a different item from v1's. The clean-up can't catch this one, because the item carries no "a plus" marker and only required lists are checked.
- **Ad 3:** the model moved two items into `other_requirements` that don't belong there:
  - the full-stack debugging skill, which is a required hard skill;
  - "Support multi-stage deployments", which is a duty.
- **Vague items:** unchanged at 12. Ad 6 still puts 4 duties into `soft_skills`.
- **Other wording:** responsibilities, locations and some item wording changed in ads 2–7. Any prompt change shifts the model's output a little, even at temperature 0. Most of these changes are neutral.

**Conclusion:** both fixes did what they were meant to, and v2 is better than v1 overall: no invented facts, no guessed seniority. The remaining weak spots are:
- skills or duties landing in `other_requirements`;
- duties landing in `soft_skills`.

Both are candidates for the next prompt rule.

**Lesson:** after changing code, restart the agent, then check `agent_version` in the result files before comparing. Prompt changes apply right away, but code changes don't.
