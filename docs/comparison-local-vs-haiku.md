# Local models vs Claude Haiku

Two set-ups, compared in two rounds:

- **Local** (`--preset local`, the default): `ministral-3:8b` for the Job Analyst, CV Matcher and Cover Letter Writer; `granite4.1:8b` for the Application Reviewer.
- **Haiku** (`--preset haiku`): `claude-haiku-5-5` for all four.

Same prompts, same JSON schemas, same plain-Python checks. Haiku runs without a temperature at its default adaptive thinking ([decisions.md](decisions.md), decision 5).

| Round | Date | What changed before it | Haiku cost |
|---|---|---|---|
| Step 1: before the fixes | 2026-11-08 | Claude added as an option | $0.022 |
| Step 1.1: after the fixes | 2026-11-09 | preferred fields for experience and other requirements; "a CV can't show this" is asked; the Reviewer gets the ad text ([decisions.md](decisions.md), decision 6) | $0.125 (incl. $0.071 for Sonnet in the planted-error test) |

**Data used:**
- the 7 real job ads from the original comparison (not committed);
- the fictional files in `samples/demo/`: 3 made-up non-AI ads, the demo ad, four fictional CVs and scripted answers.

No real CV was used. All spend is counted by the budget guard.

**Scores:** every score uses the [scorecard rules](model-comparison-job-analyst.md#scoring-rules-used) with the **strict reading**:
- a preferred item in a required field counts as a wrong field;
- a list item that isn't a requirement on the candidate (a hiring note, a contract option) counts as vague;
- long "X, Y or Z" alternative lines are not counted as vague.

Scores marked **model-read** were drafted by Claude and still need a human spot-check; every counted item is listed below.

## (a) Job Analyst, existing scorecard

### Before and after the fixes

**7 AI job ads**

| Scorecard | Local before | Haiku before | Local after | Haiku after |
|---|---|---|---|---|
| Seniority guessed without a signal (6 ads) | 0 of 6 | 0 of 6 | 0 of 6 | 0 of 6 |
| "Or equivalent experience" rule followed (3 ads) | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| Required vs preferred: items in the wrong field | 3 | 7 | **0** | **0** |
| Travel and certifications captured (3 items) | 3 of 3 | 3 of 3 | 3 of 3 | 3 of 3 |
| Vague items or full sentences | 13 | 3 | 15 | 5 |
| Invented facts | 0 | 0 | 0 | 0 |
| Seconds, total (average per ad) | 156.7 (22.4) | 55.9 (8.0) | 168.6 (24.1) | 57.6 (8.2) |
| Cost | $0 | $0.010 | $0 | $0.009 |

**3 made-up non-AI ads** (bartender, nurse, accountant)

| Scorecard | Local before | Haiku before | Local after | Haiku after |
|---|---|---|---|---|
| Seniority guessed without a signal (2 ads) | 0 of 2 | 0 of 2 | 0 of 2 | 0 of 2 |
| "Or equivalent" rule followed (1 ad) | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| Items in the wrong field | 2 | 3 | **0** | **0** |
| Travel and certifications captured (4 items) | 4 of 4 | 4 of 4 | 4 of 4 | 4 of 4 |
| Vague items or full sentences | 2 | 2 | 5 | 1 |
| Invented facts | 1 | 0 | 1 | 0 |
| Seconds, total (average per ad) | 41.3 (13.8) | 15.8 (5.3) | 44.0 (14.7) | 14.9 (5.0) |
| Cost | $0 | $0.003 | $0 | $0.003 |

**Where the "before" numbers come from:**
- **Local before:** the hand scores from [model-comparison-job-analyst.md](model-comparison-job-analyst.md), now read strictly. On the 7 ads this changes two counts:
  - wrong field 1 → 3: ad 6 "European customers" (strongly preferred) and ad 7 travel (preferred), both in required fields;
  - vague 12 → 13: ad 2 lists the hiring note "in-person interviews" as a requirement.

  The made-up ads didn't change: every item there was already counted.
- **Haiku before:** model-read in step 1. The items are listed in the step 1 section below.
- **"After" columns:** model-read in step 1.1. The items are listed next.

### After the fixes, per ad (local / Haiku), model-read

| Ad | Seniority guessed | Or-equivalent | Wrong field | Travel / certs | Vague / sentences | Invented |
|---|---|---|---|---|---|---|
| 1 | no / no | n/a | 0 / 0 | n/a | 0 / 1 | 0 / 0 |
| 2 | no / no | yes / yes | 0 / 0 | n/a | 1 / 0 | 0 / 0 |
| 3 | no / no | yes / yes | 0 / 0 | n/a | 2 / 1 | 0 / 0 |
| 4 | no / no | n/a | 0 / 0 | travel: yes / yes | 1 / 0 | 0 / 0 |
| 5 | no / no ("Sr": "senior") | n/a | 0 / 0 | n/a | 2 / 2 | 0 / 0 |
| 6 | no / no | n/a | 0 / 0 | n/a | 6 / 0 | 0 / 0 |
| 7 | no / no | yes / yes | 0 / 0 | both / both | 3 / 1 | 0 / 0 |
| Bartender | no / no | n/a | 0 / 0 | cert: yes / yes | 1 / 1 | 0 / 0 |
| Nurse | no / no | yes / yes | 0 / 0 | cert: yes / yes | 4 / 0 | 0 / 0 |
| Accountant | no / no ("Senior": "senior") | n/a | 0 / 0 | both / both | 0 / 0 | 1 / 0 |

**The items behind the "after" numbers (for the spot-check):**

- **Haiku, vague (6):**
  - ad 1: "Hands-on expertise designing and building enterprise AI and agentic AI solutions" (11 words copied);
  - ad 3: "Full-stack debugging across application code, APIs, model endpoints, orchestration, retrieval, infrastructure, and security" (13 words);
  - ad 5: "Voice output tuning (SSML, lexicons, regex)" and "Structured testing of architecture and AI agent performance" (duties from the task list, listed as skills);
  - ad 7: "Producing solution blueprints, work estimates, delivery plans, staffing models, SOW inputs, and pricing inputs" (several items in one, 13 words);
  - bartender: "Valid food hygiene certificate, or willingness to get one in first month" (12 words).
- **Local, vague (20):**
  - ad 2: "Novel technical problems, ambiguity, bug diagnosis, architectural solutions" (several in one);
  - ad 3: a 16-word "debugging across full stack (...)" item, and a 13-word responsibility;
  - ad 4: an 18-word copy of the client-facing experience line;
  - ad 5: "CRMs, ERPs, ticketing systems, contact center platforms" (several in one) and "SSML, Lexicons, Regex" (a duty, three tools in one item);
  - ad 6: soft skills "Technical credibility" (a fragment), plus "Solution design support", "Technical discovery" and "Technical presentations" (duties); a duty turned into a requirement ("Experience with European data residency, security, GDPR, AI Act"); a 14-word responsibility;
  - ad 7: "delivery roles", "assumptions", "dependencies" (fragments, split from the experience lines);
  - bartender: the 11-word certificate item;
  - nurse: "Electronic patient record documentation", "Vital signs monitoring", "Medication administration", "Wound care" (duties listed as required hard skills; the ad lists no hard skills).
- **Local, invented (1):** accountant German level "very good" (the ad says fluent).
- **Borderline, not counted:**
  - the long "or" alternative lines (ads 2, 3, 6, 7);
  - nurse soft skills "Collaboration with doctors / physiotherapists / social services" (local);
  - Haiku ad 6 lists three of the company's own product names (from the task list) as required skills.

### What changed with the fixes

- **Required vs preferred is fixed for both models: 0 wrong-field items on 10 ads.** Before, it was 5 (local, strict) and 10 (Haiku).
  - The new fields `experience_preferred` and `other_requirements_preferred` took every preferred experience item and preferred certificate.
  - Haiku now uses them directly, and the marker clean-up (the safety net) didn't have to move anything.
- **Vague items went up locally (15 against 13; 5 against 2 on the made-up ads).** The longer prompt shifted `ministral-3:8b` at temperature 0: it now fills required hard skills with duties (nurse) and splits experience lines into fragments (ad 7). Haiku stayed low (6 against 5).
- **A new Haiku issue, not on the scorecard:** in ad 3 it lists the six "ways to stand out" items twice, in `experience_preferred` and in `hard_skills_preferred`, so they count double as preferred points. The clean-up only removes exact duplicates (backlog).
- **"Such as A, B or C" alternatives still differ:**
  - local still splits the ad 1 frameworks into four required items;
  - both models now split ad 6's "at least two of these domains" into separate required skills.
- **The array-limit check acted for the first time:** Haiku returned 8 responsibilities for ad 5, and plain Python cut them to the schema's 6.
- **Haiku now finds the ad 6 company name** (it missed it in step 1).

## (b) End to end: three dummy CVs (step 1.1)

Three fictional CVs for the fictional demo ad: Jane Doe (strong fit), Robin Sample (medium fit) and Casey Placeholder (weak fit). The expected outcomes were written and committed **before any run**: [samples/demo/expected_outcomes.md](../samples/demo/expected_outcomes.md). Each CV has its own scripted answers.

| CV | Expected | Local | Haiku |
|---|---|---|---|
| Jane Doe | 85–100%, shortlist | 100%, shortlist ✓ | 100%, 100%, 100% ✓; shortlist, **maybe**, shortlist |
| Robin Sample | 55–75%, maybe | 74%, maybe ✓ | **76%** (1 point above the range), maybe |
| Casey Placeholder | 0–20%, reject | 10%, reject ✓ | 3%, reject ✓ |

| Run | Score (points) | Verdict | CV Matcher questions | Claims proven / unproven | Reviewer items dropped | Seconds: Job Analyst / Matcher / Letter / Reviewer = total | Cost |
|---|---|---|---|---|---|---|---|
| Local, Jane | 100% (31/31) | shortlist | travel, RAG | 12 / 0 | 0 | 15 / 29 / 47 / 44 = 135 | $0 |
| Local, Robin | 74% (23/31) | maybe | travel, degree, SQL, PostgreSQL | 10 / 0 | 0 | 24 / 26 / 42 / 48 = 140 | $0 |
| Local, Casey | 10% (3/31) | reject | travel, years, English | 7 / 1 (after a rewrite) | 0 | 25 / 21 / 65 / 45 = 156 | $0 |
| Haiku, Jane 1 | 100% (33/33) | shortlist | travel | 14 / 0 | 0 | 3 / 11 / 26 / 15 = 56 | $0.0081 |
| Haiku, Jane 2 | 100% (34/34) | maybe | travel | 14 / 0 | 0 | 2 / 9 / 26 / 19 = 56 | $0.0076 |
| Haiku, Jane 3 | 100% (31/31) | shortlist | travel | 12 / 0 | 0 | 6 / 7 / 22 / 22 = 57 | $0.0084 |
| Haiku, Robin | 76% (25/33) | maybe | travel, degree, SQL, FastAPI or Django, English | 10 / 0 | 0 | 3 / 8 / 31 / 11 = 52 | $0.0074 |
| Haiku, Casey | 3% (1/31) | reject | years, degree, English | 10 / 0 | 0 | 3 / 5 / 25 / 10 = 43 | $0.0060 |

**What this shows:**
- **The predictions held:** 5 of 6 outcomes are inside the predicted range with the predicted verdict. Haiku's Robin is 1 point above the range, with the right verdict.
- **"A CV can't show this" works.** Travel was asked first in 7 of 8 runs.
  - In the 8th (Haiku, Casey), the Job Analyst didn't list the travel requirement at all, so there was nothing to ask about.
  - That's a Job Analyst miss, not a matcher-rule miss: the extraction varies from run to run without a temperature.
- **Gaps were found as predicted.**
  - Robin: FastAPI or Django, RAG, and AWS or Azure missing in both set-ups.
  - Casey: missing almost everything.
  - Jane: no gaps.
- **Local still asks about things the CV states plainly.** It asked Jane about RAG, and Robin about SQL and PostgreSQL. Haiku asked Jane nothing but travel.

### How much a Haiku run varies (Jane Doe, 3 runs)

- **Score: stable,** 100% in all three. The checklist size wasn't stable: 31, 33 and 34 points, because run 2's Job Analyst listed German twice.
- **Verdict: not stable,** shortlist, maybe, shortlist. The same strong CV can get different verdicts.
  - **Run 2's "maybe"** rests on one flagged sentence about solving "the same problem at a larger scale", which comes from the candidate's own answer.
  - **Run 3's reviewer** said the CV's jobs since 09/2019 add up to "about six years", so "seven years" was an overstatement. They add up to seven. The agents are never told today's date, so the model guessed it (new backlog item).
- **Cost and time: stable,** $0.0076–$0.0084 and 56–57 seconds per run.

## (c) Planted errors: a tiny Reviewer test (step 1.1)

**The set-up** (committed before the runs): one Haiku-written letter for Jane Doe, copied, with 4 planted mistakes. All four can be detected from the Reviewer's input; see [samples/demo/planted_errors/planted_errors.md](../samples/demo/planted_errors/planted_errors.md).
- **Mistake 3** (a true but irrelevant claim) has a caveat: the rubric has no "irrelevant" category, only "generic phrases".
- **Mistake 4** (a wrong company fact) can only be seen since the Reviewer gets the ad text.

Same Reviewer agent, same prompt, same input; only the model changed.

| Run | Twelve years (inflated) | Terraform (not in CV) | Rowing club (irrelevant) | Airlines (wrong company fact) | Caught | False alarms | Other flags (fair points) | Cost |
|---|---|---|---|---|---|---|---|---|
| Haiku 1 | caught | caught | missed | caught | 3 of 4 | 0 | 2 | $0.0024 |
| Haiku 2 | caught | caught | missed | caught | 3 of 4 | 0 | 3 | $0.0024 |
| Sonnet 1 (`claude-sonnet-5-5`) | caught | caught | caught | caught | 4 of 4 | 0 | 2 | $0.0375 |
| Sonnet 2 | caught | caught | caught | caught | 4 of 4 | 0 | 2 | $0.0332 |

- **Both models caught the three factual errors in both runs:**
  - each was quoted as an overclaim with the correct reason ("the CV states 7 years", "Terraform does not appear in the CV", "the job ad says freight companies");
  - each also turned up as an interview question.
- **Only Sonnet caught the irrelevant claim,** in both runs, as "irrelevant filler". Haiku didn't flag it.
- **Other flags were fair points, not false alarms.** Every run flagged "only at a larger scale" (an assumption the ad doesn't support) and a generic motivation line; one Haiku run also flagged the generic opening sentence. No run flagged a correct, specific sentence.
- **Cost:** Sonnet cost about 15 times as much per review ($0.035 against $0.0024).

**Call it what it is:** one letter, four mistakes, two runs per model. It shows that the ad-text fix lets a reviewer catch a wrong company fact, and that Sonnet noticed irrelevance where Haiku didn't, here. It doesn't measure reviewer quality.

## Step 1 details (before the fixes, 2026-11-08)

**Haiku's wrong-field items (10).** Each was a preferred item in a required field, marked as such:
- ad 2: three "(preferred)" qualifications in `experience_details`;
- ad 3: a "(preferred)" background item in `experience_details`;
- ad 6: "(strongly preferred)" European customers in `experience_details`;
- ad 7: travel and certifications in `other_requirements`, both "(preferred)";
- nurse: "Ideally 2 years on a surgical ward" and "Intensive care (a plus)" in `experience_details`;
- accountant: "Bilanzbuchhalter IHK (a plus)" in `other_requirements`.

**Haiku's vague items (5):**
- ad 2: "In-person interviews in most instances";
- ad 5: "SSML, lexicons, regex";
- ad 6: a 13-word copied sentence;
- bartender: a 12-word certificate item, and "Full-time or part-time".

**End to end on the original demo CV** (one run each, scripted answers):

| | Local | Haiku |
|---|---|---|
| Score, verdict | 87%, shortlist | 88%, maybe |
| Claims proven / unproven, reviewer items dropped | 9 / 0, 0 | 12 / 0, 0 |
| Total time, cost | 116 s, $0 | 54 s, $0.0079 |

Back then:
- both models marked travel *missing* instead of asking (fixed in step 1.1);
- Haiku's Reviewer flagged true company facts as overclaims because it never saw the ad's company description (fixed in step 1.1).

## Limits

- **Small samples:** 7 real ads of one kind (senior AI roles), 3 short made-up ads, one demo ad and four fictional CVs.
- **Single runs mostly.** Only Haiku Jane Doe ran three times. Haiku has no temperature setting and the local letter writer runs at 0.4, so letters and verdicts vary.
- **Model-read scores:** the scores in (a) after the fixes, and Haiku's before them, were drafted by Claude, a model from the same family as one of the two being scored.
- **Same family reviewing itself:** with `--preset haiku`, the Reviewer is the same model family as the agents it reviews. The plain-Python grounding checks are the independent layer. The planted-error test is a first, tiny look at that question.
