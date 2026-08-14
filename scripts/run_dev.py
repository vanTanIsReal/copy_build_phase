"""Dev server launcher for Windows.

Why this exists instead of `uvicorn src.main:app --reload ...`: AsyncPostgresSaver (the agent's
persistent memory - the project requires Postgres, no SQLite fallback) needs psycopg's async
mode, which cannot run on Windows' default ProactorEventLoop - it needs SelectorEventLoop.
Uvicorn's Windows subprocess setup selects SelectorEventLoop when reload is enabled.  We also set
the policy in the parent process, then pass the supported ``"asyncio"`` loop name.  Passing an
event-loop class used to work in older Uvicorn releases, but raises ``KeyError`` in Uvicorn 0.35+.

Usage:
    python scripts/run_dev.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True, loop="asyncio")
