# Planted errors (listed before any Reviewer run)

A tiny test of the Application Reviewer: 4 planted mistakes in one letter, 4 Reviewer runs. It shows what a reviewer catches here. It doesn't measure reviewer quality in general.

**The letter:** `letter_original.md` was written by Claude Haiku in a demo run for the fictional Jane Doe (`../cv_jane_doe.pdf`, run `2026-11-09_09-04-19`). All of its claims were proven by the plain-Python claims check. `letter_planted.md` is a copy with 4 mistakes planted.

**The Reviewer's input** is the same in every run: `requirements.json` and `match_report.json` from that run, `job_ad.txt` (the demo ad), the CV, and `letter_planted.md`. The prompt is `prompts/application_reviewer.md`.

## The 4 mistakes

| # | Type | Planted sentence | Why it's wrong | Can the Reviewer's input reveal it? |
|---|---|---|---|---|
| 1 | a skill not in the CV | "I also wrote all of our cloud infrastructure as code in Terraform." (S5) | The CV never mentions Terraform or infrastructure as code. | **Yes:** the CV text is in the input. |
| 2 | inflated years of experience | "With **twelve** years of professional Python experience and three years of building LLM features in production, ..." (S2; the original says "seven") | The CV says "7 years of professional experience", and its jobs start in 09/2019. | **Yes:** the CV text is in the input. |
| 3 | a claim the ad never asked for | "In my free time I maintain the website of a local rowing club." (S8) | True (the CV lists it under volunteering), but nothing in the ad asks for it. It's filler for this job. | **Yes, with a caveat:** the ad text is in the input, so irrelevance can be seen. But the rubric has no "irrelevant" category; only "generic phrases" (filler) comes close. |
| 4 | a wrong fact about the company | "I also know Lumenpath from its route-planning software for passenger airlines." (S10) | The ad says Lumenpath builds software for mid-sized **freight** companies. Airlines appear nowhere. | **Yes, since the fix:** only the original ad text (new Reviewer input in step 1.1) shows what the company does. The Job Analyst's fields don't. |

S2, S5, S8 and S10 are the numbers these sentences get in the Reviewer's numbered LETTER SENTENCES list.

## How the runs are counted (decided before the runs)

- **Caught:** the planted sentence is quoted in `overclaims` or `generic_phrases` (and survives the grounding check), or a top weakness or interview question clearly names the mistake (e.g. Terraform, twelve years, airlines, rowing club).
- **Missed:** none of the above.
- **Other flags:** every quoted sentence that isn't one of the 4. Each is judged:
  - **false alarm:** the sentence is supported by the CV, the ad or the candidate's answer, and isn't filler;
  - **fair point:** a real weakness of the original letter, e.g. a generic closing line.

## The runs

The same Reviewer agent, the same prompt and the same input, with only the model changed (set at startup):
- Claude Haiku 5.5 (`claude-haiku-5-5`): 2 runs
- Claude Sonnet 5.5 (`claude-sonnet-5-5`): 2 runs

```
python -m scripts.try_reviewer samples/demo/planted_errors samples/demo/cv_jane_doe.pdf \
    --letter samples/demo/planted_errors/letter_planted.md --out results/planted/<model>-<n>
```
