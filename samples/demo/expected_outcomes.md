# Expected outcomes for the dummy CVs (written before any run)

Written on 2026-11-09, before any run with these CVs, so the runs can be compared with a prediction instead of being judged afterwards. All three people and their companies are fictional. They apply to the fictional demo ad `job_ad_demo.txt` (Backend & AI Engineer at Lumenpath Logistics).

**How to read the ranges:** the score depends on the Job Analyst's checklist, which differs between models and runs (31 to 33 points in earlier demo runs). So each CV gets a range, not a number. Scripted answers are in `answers_<name>.json`.

**What the demo ad asks for:**
- **Required:** 3+ years as a backend engineer; Python and SQL; FastAPI or Django; PostgreSQL and REST API design; LLMs and RAG; Docker and CI/CD; AWS or Azure; a Bachelor's in CS or equivalent; fluent English; occasional customer travel (about 10%).
- **Preferred:** Kubernetes, evaluation of LLM output, German.

**For every CV:** "occasional travel to customers" can't be shown in a CV. With the new rule it must be **asked** in every run (local and Haiku), never marked missing.

## Jane Doe (`cv_jane_doe.pdf`): strong fit

| | Expected |
|---|---|
| Score | 85–100% |
| Verdict | shortlist |
| Key matches | a customer-facing RAG assistant in production, with an evaluation set; REST APIs in Python with FastAPI and PostgreSQL; Docker, Kubernetes on AWS, GitLab CI/CD |
| Key gaps | none on the required list. Travel is asked (she answers yes). |
| Questions | travel; maybe items the model finds only in her skills list |

## Robin Sample (`cv_robin_sample.pdf`): medium fit

| | Expected |
|---|---|
| Score | 55–75% |
| Verdict | maybe |
| Key matches | 3 years of backend REST APIs (Java, Spring Boot) with PostgreSQL; Docker and GitHub Actions CI; Python scripts and SQL |
| Key gaps | no FastAPI or Django; no RAG (an LLM hackathon prototype only); no AWS or Azure (on-premises). Preferred: no Kubernetes, no LLM evaluation (German: yes). |
| Questions | travel (yes); probably the degree (Business Informatics: answers yes, a related field); maybe English level (C1: answers yes) |

## Casey Placeholder (`cv_casey_placeholder.pdf`): weak fit

| | Expected |
|---|---|
| Score | 0–20% |
| Verdict | reject |
| Key matches | almost none for the role. German (preferred) and willingness to travel (asked: yes). |
| Key gaps | no backend experience, no Python or SQL, no Docker or CI/CD, no cloud, no LLM work, no CS degree; English B2, not fluent |
| Questions | travel (yes); English (no); the 3 days in the Hamburg office if the model asks (no: lives in Munich) |

## What would be a surprise

- **Travel marked "missing"** or not asked, in any run: the new rule failed.
- **Jane below 85% or not shortlisted:** the matcher or the reviewer misses clear proof.
- **Robin shortlisted or rejected:** the verdict doesn't reflect a partial fit.
- **Casey above 20%:** the matcher accepts weak proof.
