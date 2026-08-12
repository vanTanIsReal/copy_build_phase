"""Dataset for scripts/eval_extract_tasks.py, split by source so the file doesn't grow into one
unmanageable list:

- `base` - the original 8 hand-written cases (unchanged, moved verbatim from
  eval_extract_tasks.py - pure refactor, not a behavior change).
- `real_conversations` - cases transcribed/paraphrased from conversations the dev team had with
  its own test accounts, deliberately steered at the failure-mode categories the original 8 cases
  didn't cover. No other user's message content was used - see that module's docstring.
- `edge_cases` - additional synthetic cases targeting specific failure modes not easily produced
  on demand in a natural conversation (ambiguous multi-speaker attribution, conflicting dates,
  code-switching, etc).

`DATASET` here is the concatenation of all three, in that order - this is what
eval_extract_tasks.py imports and scores as one dataset (same global micro-averaged P/R/F1/date
accuracy as before, just sourced from more than one file now).
"""

from scripts.eval_data import base, edge_cases, real_conversations
from scripts.eval_data.schema import EvalCase, ExpectedTask, next_weekday

DATASET: list[EvalCase] = base.DATASET + real_conversations.DATASET + edge_cases.DATASET

__all__ = ["DATASET", "EvalCase", "ExpectedTask", "next_weekday"]
