# Local models vs Claude Haiku (2026-11-08)

Upgrade step 1 made Claude Haiku an option for every agent (see decision 5 in [decisions.md](decisions.md)). This page compares the two set-ups:

- **Local:** `ministral-3:8b` for the Job Analyst, CV Matcher and Cover Letter Writer, `granite4.1:8b` for the Application Reviewer (`--preset local`, the default).
- **Haiku:** `claude-haiku-5-5` for all four (`--preset haiku`).

Same prompts, same JSON schemas, same plain-Python checks. Haiku runs without a temperature (the API no longer accepts one) at its default adaptive thinking; see [decisions.md](decisions.md) for why.

**Data used:** the 7 job ads from the original comparison (not committed) and the fictional files in `samples/demo/` (3 made-up non-AI ads, the demo ad, the demo CV and scripted answers). No real CV was used.

**Total cost of every Haiku call in this comparison:** $0.022 (15 calls), counted by the budget guard in `results/cloud_spend.json`.

## (a) Job Analyst, existing scorecard

Same ads, same rules as [model-comparison-job-analyst.md](model-comparison-job-analyst.md#scoring-rules-used).

- **Local column:** the hand scores from that page. The local output was re-run today with the new code and is **identical, item for item**, to the scored output (all 10 ads), so those scores still apply. The local times are from today's run.
- **Haiku column: model-read.** Claude drafted these scores by the same rules; they still need a human spot-check. Every counted item is listed below, so the check is quick.

### 7 AI job ads

| Scorecard | Local (`ministral-3:8b`) | Haiku (`claude-haiku-5-5`), model-read |
|---|---|---|
| Seniority guessed without a signal (6 ads) | 0 of 6 | 0 of 6 |
| "Or equivalent experience" rule followed (3 ads) | 3 of 3 | 3 of 3 |
| Required vs preferred: items in the wrong field | 1 (strict re-read: 3, see below) | **7** |
| Travel and certifications captured (3 items) | 3 of 3 | 3 of 3 |
| Vague items or full sentences | 12 | **3** |
| Invented facts | 0 | 0 |
| Seconds, total (average per ad) | 156.7 (22.4) | **55.9 (8.0)** |
| Cost | $0 | $0.010 |

### 3 made-up non-AI ads (bartender, nurse, accountant)

| Scorecard | Local | Haiku, model-read |
|---|---|---|
| Seniority guessed without a signal (2 ads) | 0 of 2 | 0 of 2 |
| "Or equivalent" rule followed (1 ad) | 1 of 1 | 1 of 1 |
| Items in the wrong field | 2 | 3 |
| Travel and certifications captured (4 items) | 4 of 4 | 4 of 4 |
| Vague items or full sentences | 2 | 2 |
| Invented facts | 1 | **0** |
| Seconds, total (average per ad) | 41.3 (13.8) | **15.8 (5.3)** |
| Cost | $0 | $0.003 |

### Per ad, Haiku (model-read)

| Ad | Seniority guessed | Or-equivalent | Wrong field | Travel / certs | Vague / sentences | Invented | Seconds |
|---|---|---|---|---|---|---|---|
| 1 | no | n/a | 0 | n/a | 0 | 0 | 7.3 |
| 2 | no | yes | 3 | n/a | 1 | 0 | 8.8 |
| 3 | no | yes | 1 | n/a | 0 | 0 | 10.3 |
| 4 | no | n/a | 0 | travel: yes | 0 | 0 | 5.3 |
| 5 | no (has "Sr", said "senior") | n/a | 0 | n/a | 1 | 0 | 6.3 |
| 6 | no | n/a | 1 | n/a | 1 | 0 | 11.1 |
| 7 | no | yes | 2 | travel + certs: both | 0 | 0 | 6.8 |
| Bartender | no | n/a | 0 | cert: yes | 2 | 0 | 4.6 |
| Nurse | no | yes | 2 | cert: yes | 0 | 0 | 6.2 |
| Accountant | no ("Senior" in title, said "senior") | n/a | 1 | travel + cert: yes | 0 | 0 | 5.0 |

### The items behind Haiku's numbers (for the spot-check)

- **Wrong field (10).** Each is a preferred item in a field the CV Matcher counts as required, and each carries a marker that says so:
  - ad 2: three "preferred qualifications" in `experience_details`, each ending in "(preferred)";
  - ad 3: a "ways to stand out" background item in `experience_details`, "(preferred)";
  - ad 6: "European customers and regulatory environments (strongly preferred)" in `experience_details`;
  - ad 7: travel and certifications in `other_requirements`, both "(preferred)";
  - nurse: "Ideally 2 years on a surgical ward" and "Experience in intensive care (a plus)" in `experience_details`;
  - accountant: "Bilanzbuchhalter IHK certification (a plus)" in `other_requirements`.
- **Vague (5):**
  - ad 2: "In-person interviews in most instances" in `other_requirements` (a hiring note, not a requirement);
  - ad 5: "SSML, lexicons, regex" (three skills in one item);
  - ad 6: "Demonstrated ability to design, build and troubleshoot complex cloud systems in production" (13 words copied);
  - bartender: "Valid food hygiene certificate or willingness to obtain one in first month" (12 words, as in the local output) and "Full-time or part-time" (a contract option, not a requirement).
- **Borderline, not counted:**
  - the long experience lines in ads 3 and 7 ("8+ years in solution architecture, technology consulting, ... or delivery roles"). They are "X or Y" alternatives, and the local output has the same lines, which the hand score didn't count;
  - ad 2 "Engaging with and presenting to technical stakeholders or executive leaders (preferred)" (11 words, also an alternative);
  - ad 7 "Security and governance considerations";
  - ad 3 "Developer playbooks".

### Strict re-read of the local hand score

Applying the written rule strictly would change two local counts:
- **Wrong field:** ad 6 "European customers and regulatory environments" (strongly preferred in the ad) and ad 7 "Ability to travel" (preferred in the ad) both sit in required fields, the same placement counted for Haiku. Strictly, local would be 3, not 1.
- **Vague:** ad 2 has the same interview note as Haiku. Strictly, local would be 13, not 12.

Haiku's counts above use the strict reading. The local hand score is left as it was, for you to decide.

### What this means

- **Haiku is cleaner and faster.**
  - Its items are short and usable: 3 vague items against 12. It never filled `soft_skills` with duties.
  - It invented nothing, and it got the accountant's German level right where the local model didn't.
  - It's about 3 times faster per ad, at roughly $0.001 per ad.
- **Haiku is worse at required vs preferred: 7 against 1 (or 3, read strictly).**
  - It reads "preferred" correctly but has nowhere to put it: the schema has preferred *skills* only. So it writes "(preferred)" or "(a plus)" inside required fields, and the CV Matcher counts those items as required.
  - Every one of its 10 wrong-field items carries such a marker. The clean-up that already moves marked items out of `hard_skills_required` would catch all of them if it also ran on `experience_details` and `other_requirements`. That's the existing backlog item "'Preferred' on experience and certificates is lost", which now has more evidence. It changes scoring, so it's your call.
- **"Such as A, B or C" alternatives: each model fails in a different place.**
  - Ad 1: Haiku kept the four agent frameworks together as one item; local split them into four required items.
  - Ad 6 ("expertise in at least two of these domains"): local kept the three domain groups as long lumped items; Haiku split them into 13 separate required skills.
  - Either way, a CV that meets the real requirement can lose points.
- **Other differences:**
  - ad 6: Haiku missed the company name, which the ad gives only inside a product name; local found it;
  - Haiku's prompt token counts are about 2.3 times the local ones for the same text, because of a different tokenizer plus the structured-output schema. About 70% of its output tokens are thinking.
  - No answer needed cutting to the schema's array limits.

## (b) End to end: demo ad + demo CV

One run each, with `samples/demo/answers_demo.json` answering every question, so both set-ups got the same answers:

```
python scripts/start_agents.py --preset local      # or --preset haiku
python -m orchestrator samples/demo/job_ad_demo.txt samples/demo/cv_demo.pdf --answers samples/demo/answers_demo.json
```

| | Local | Haiku |
|---|---|---|
| Match score | 87% (27 of 31 points) | 88% (29 of 33 points) |
| CV Matcher questions | 3 (SQL, PostgreSQL, CI/CD; answered yes) | none |
| Letter: claims proven / unproven | 9 / 0 | 12 / 0 |
| Letter: rewrite needed | no | no |
| Letter length | 216 words (style warning: under 250) | 229 words (same warning) |
| Reviewer verdict | shortlist | maybe |
| Overclaims flagged | 2 | 3 |
| Reviewer items dropped (quote not in the letter) | 0 | 0 |
| Clichés added by the code check | 0 | 0 |
| Seconds: Job Analyst / CV Matcher / Letter / Reviewer | 20.4 / 23.3 / 36.3 / 35.9 | 5.1 / 11.5 / 21.4 / 15.5 |
| Seconds, total | 115.8 | 53.5 |
| Tokens in / out | 7,573 / 2,181 | 15,225 / 12,719 |
| Cost | $0 | $0.0079 |

**What the numbers don't show:**
- **CV Matcher:**
  - Haiku found SQL, PostgreSQL and CI/CD in the CV's skills list, with quotes, so it asked nothing. The local model marks them "unclear" and asks (backlog: "Items the CV lists plainly are marked unclear").
  - Both models marked "occasional travel to customers" as *missing* instead of *unclear*, so the candidate was never asked, although willingness to travel can't be in a CV (new backlog item).
- **Reviewer, local (`granite4.1:8b`):**
  - It repeated the known false positive "no proof of SQL or PostgreSQL" (the CV lists both).
  - It called the letter credible: shortlist.
- **Reviewer, Haiku:**
  - Its top weaknesses are more concrete: no customer-facing AI work, travel not addressed.
  - But two of its three "overclaims" are sentences built from the candidate's own answer about the company. It said "the job data does not mention shipping data or freight companies", yet the ad's "About us" does.
  - The cause is the Reviewer's input, not the model: the Reviewer only gets the Job Analyst's fields (title, company, skills, responsibilities), never the ad's company description (new backlog item).
  - Those false positives are part of why Haiku said "maybe".

## Limits of this comparison

- **One run per set-up end to end.** Haiku has no temperature setting, and the local letter writer runs at 0.4, so letters and verdicts vary from run to run. Treat (b) as one example, not a measurement.
- **Model-read scores.** The Haiku scores in (a) were drafted by Claude, a model from the same family as the one being scored. The item list above exists so a human can check them.
- **Same family reviewing itself.** With `--preset haiku`, the Reviewer is the same model family as the agents it reviews, so it may share their blind spots. The grounding checks in plain Python (quotes must exist in the CV or letter) are the independent layer. Planned next: a planted-error test with Sonnet as the Reviewer.
- **Small sample:** 7 real ads of one kind (senior AI roles), 3 short made-up ads, and one demo CV.
