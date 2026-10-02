# Competition rules — decisions (P1), recorded 2026-10-02

Source: Rules tab text pasted by the user (Google – The Gemma 4 Developer Agent Competition).

## Answers that change the plan
| Question | Rule | Decision |
|---|---|---|
| External data (SWE-bench, SWE-Gym, SWE-smith, mined history)? | §2.6a/b: allowed if publicly available and equally accessible at no / minimal cost | **Allowed.** B3 and E3 unblocked. Log provenance + license per dataset. |
| External models / tools? | §2.6b: allowed unless host prohibits; must be reasonably accessible, minimal cost | Allowed for development (e.g. synthetic issue generation). Submission itself must still use only `gemma-4-31b-it-qat-w4a16-ct` (harness rule). |
| Open-source code in the solution | §3.6c: only OSI-approved licenses that do not limit commercial use | Check licenses of any code/data we build on (MIT/Apache/BSD OK; no GPL-incompatible-with-commercial, no NC licenses). |
| Winner obligations | §2.5, §2.8: Apache-2.0-compatible license; deliver training + inference code, environment description, reproducible write-up | Keep everything reproducible from this repo (scripts, configs, data provenance). |
| Submissions | §2.2: **1 per day**; up to **2 final submissions** | Plan submissions; public LB is not a selection criterion (§8 of plan). |
| Team | §2.1: max 5; merges allowed | — |
| Private sharing | §3.5d / §3.6a: no private sharing of code/data outside the Team | All collaborators (incl. Kaggle account `vedantmoghe` used for eval kernels) must be on the same Kaggle Team. Kernels stay private. |
| Competition data | §2.4b: do not redistribute to non-participants | `data/` is gitignored; never push snapshots/tasks to public repos or public datasets. The private `gemma-rl-test-wheels` dataset contains only PyPI wheels. |
| Hand labeling | §3.4b: no hand labeling / human prediction of validation or test records | Training on the 129 public tasks' gold patches is fine (competition data, automatic). Never hand-label hidden test data (we can't see it anyway). |

## Licenses to verify before use (B3 / E3)
- SWE-bench (MIT), SWE-Gym, SWE-smith — confirm dataset + source-repo licenses at ingestion time; record in `data/derived/provenance.jsonl`.
