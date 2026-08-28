# Evaluation Evidence — Orbit

Generated at `2026-08-28T06:00:21.415828+00:00` from source revision `f37cce4`
with uncommitted evaluation changes.

This report never converts missing evidence into a passing score. `PENDING` means the runner or
protocol exists but no current result artifact is available.

## 1. Release evidence summary

| Evidence | Result | Gate | Status |
|---|---:|---:|---|
| Automated tests | 410/410 passed, 0 skipped | No failures/errors | PASS |
| Source coverage | 66.7% | >=60% | PASS |
| Formal Agent acceptance | 29.4% case pass | Dataset gates | FAIL |
| Task title F1 | 83.3% | >=85% product gate | FAIL |
| Deadline accuracy | 100.0% | >=90% product gate | PASS |
| RAGAS grounding | 66.7% faithfulness | All RAGAS gates | FAIL |
| API latency P95 | 21.2 ms | Configured runner gate | PASS |
| User feedback | Pending | >=5 participants | PENDING |

## 2. Current measured AI quality

- Formal acceptance: `2026-08-28T05:57:27.076656+00:00` using
  `openai/openai/gpt-5.6-luna`.
- Task extraction: `13` cases; title precision
  `83.3%`, recall
  `83.3%`, F1 `83.3%`.
- The task runner's internal threshold is 70%, but the canonical product gates in `metric.md` require
  precision >=90%, recall >=80%, F1 >=85% and deadline accuracy >=90%; release status follows the
  stricter product gates.
- Missing or failed gates remain release risks even when deterministic unit tests pass.

## 3. Reproducible commands

```powershell
python scripts/run_coverage.py
python scripts/benchmark_api_latency.py --base-url http://127.0.0.1:8000 --endpoint /health
python scripts/eval_user_agent.py
python scripts/eval_extract_tasks.py
python scripts/eval_ragas.py
python scripts/summarize_user_feedback.py
python scripts/generate_evaluation_evidence.py
```

## 4. Traceability and evidence locations

- Requirement-to-test-to-code map: [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md)
- Manual scenarios: [`../MANUAL_TEST_CASES.md`](../MANUAL_TEST_CASES.md)
- Screenshot/video evidence: [`../Deliverables/evidence/`](../Deliverables/evidence/)
- Formal acceptance: [`results/agent_acceptance_latest.md`](results/agent_acceptance_latest.md)
- Evaluation protocols and commands: [`README.md`](README.md)

## 5. Evidence still requiring human/external execution

- RAGAS and formal Agent evaluation require real model credentials and consume quota.
- User satisfaction requires real anonymized participants; no synthetic rating is accepted.
- Latency must be measured against the actual target environment and recorded with its URL/model.
- Coverage/JUnit artifacts must be regenerated after material source changes.
