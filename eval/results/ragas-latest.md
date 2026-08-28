# RAGAS Evaluation Evidence

- Run at: `2026-08-28T05:42:25.528824+00:00`
- Dataset: `eval\ragas\conversation_summary_cases.jsonl` (5 cases)
- Application model: `openai/gpt-5.6-luna`
- Evaluator: `openrouter/openai/gpt-5.6-luna`
- Embeddings: `openai/text-embedding-3-small`
- Release gate: **FAIL**

| Metric | Score | Gate | Status |
|---|---:|---:|---|
| `faithfulness` | 0.667 | >= 0.70 | FAIL |
| `answer_relevancy` | 0.405 | >= 0.70 | FAIL |
| `context_precision` | 0.844 | >= 0.60 | PASS |
| `context_recall` | 1.000 | >= 0.60 | PASS |
