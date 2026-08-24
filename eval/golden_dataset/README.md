# Orbit golden conversation dataset

`cases.jsonl` contains 120 synthetic, de-identified conversations for offline evaluation. Each
line is one JSON object so runners can stream the dataset and report independent slices.

## Slices

| Primary category | Cases |
|---|---:|
| extraction | 24 |
| routing | 24 |
| permission | 24 |
| prompt_injection | 24 |
| hitl | 24 |

Cases may also carry secondary `tags`. All timestamps are fixed and use `Asia/Ho_Chi_Minh` so
relative-date expectations remain deterministic. `expected_policy` is one of `ALLOW`, `DENY`,
`MASK`, or `ASK_CLARIFY`; `expected_route` is one of `employee`, `manager`, `executive`,
`clarify`, or `deny`.

Run the structural checks with:

```powershell
pytest tests/test_golden_dataset.py -q
```

The data is intentionally synthetic. Do not replace it with production chat exports or real
employee identifiers.
