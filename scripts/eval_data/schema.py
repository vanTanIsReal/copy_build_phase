"""Shared dataclasses for the extract_tasks eval dataset - see scripts/eval_extract_tasks.py for
the scoring algorithm that consumes these (`_score_case`/`_check_date`), which this schema must
stay compatible with: greedy keyword matching against `title`, date-check nested inside a title
match, global micro-averaged aggregation across the whole dataset. Do not change the scoring
contract here - only add cases in base.py/real_conversations.py/edge_cases.py.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta


def next_weekday(base: date, weekday: int) -> date:
    """Next occurrence of `weekday` (0=Monday..6=Sunday) on/after `base` - today counts as
    "this Friday" if today already is Friday, matching how people actually mean it."""
    return base + timedelta(days=(weekday - base.weekday()) % 7)


def next_week_weekday(base: date, weekday: int) -> date:
    """`weekday` in the calendar week AFTER `base`'s week - for Vietnamese "tuần sau" (next week)
    phrases, which unlike next_weekday() above always skip the current week even if `base` itself
    is that weekday (e.g. "thứ Hai tuần sau" said on a Monday means next Monday, not today)."""
    this_monday = base - timedelta(days=base.weekday())
    return this_monday + timedelta(days=7 + weekday)


@dataclass
class ExpectedTask:
    # Case-insensitive substrings expected in a predicted task's title - any one matching counts,
    # since extract_tasks always titles in Vietnamese and there's more than one valid phrasing.
    keywords: tuple[str, ...]
    # Expected calendar date, resolved against the actual "today" at eval time (not hardcoded -
    # the dataset uses relative phrases like "tomorrow"/"this Friday", same as real conversations
    # would). None means this item isn't expected to carry a date at all.
    expected_date: Callable[[date], date] | None = None
    # Optional expected hour-of-day range (inclusive) for items with an explicit time-of-day
    # mentioned, e.g. "3h chiều" (3pm) -> (14, 16). None skips the hour check.
    expected_hour_range: tuple[int, int] | None = None


@dataclass
class EvalCase:
    name: str
    conversation: str
    expected: list[ExpectedTask] = field(default_factory=list)
