#!/usr/bin/env python3
"""Extract Codex user prompts from local session transcripts into .ai-log.

Codex writes local JSONL transcripts to ~/.codex/sessions. This scanner is
called by the git pre-push hook, so it works in Codex environments that don't
run project-level prompt hooks.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

VN_TZ = timezone(timedelta(hours=7))
DEFAULT_LOOKBACK_HOURS = 168


def git(*args: str) -> str:
    try:
        repo_cwd = Path(__file__).resolve().parent.parent
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.DEVNULL, cwd=repo_cwd
        ).strip()
    except Exception:
        return ""


def norm_path(value: str) -> str:
    return value.strip().lower().replace("/", "\\").rstrip("\\")


def parse_time(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def logged_ids(log_dir: Path) -> set[str]:
    """Read IDs from live, pending, and archived logs to prevent re-submission."""
    ids = set()
    files = [log_dir / "session.jsonl"]
    files.extend(log_dir.glob("session.pending.*.jsonl"))
    files.extend((log_dir / "archive").glob("*.jsonl"))
    for log_file in files:
        if not log_file.exists():
            continue
        try:
            lines = log_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry_id = json.loads(line).get("entry_id")
                if entry_id:
                    ids.add(entry_id)
            except (json.JSONDecodeError, AttributeError):
                pass
    return ids


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _belongs_to_repo(items: list[tuple[int, dict]], repo_root: str) -> bool:
    """Accept repo sessions and parent-workspace sessions that touched this repo."""
    session_cwd = ""
    for _, item in items:
        if item.get("type") == "session_meta":
            session_cwd = norm_path((item.get("payload") or {}).get("cwd", ""))
            break
    if session_cwd == repo_root or session_cwd.startswith(repo_root + "\\"):
        return True

    # Codex Desktop is commonly opened at Build_Phase rather than P-132. Only
    # claim such a session if a tool payload actually references P-132, so a
    # sibling repository's prompts cannot be attributed here accidentally.
    repo_slash = repo_root.replace("\\", "/")
    for _, item in items:
        for value in _strings(item):
            normalized = value.lower().replace("\\\\", "\\")
            if repo_root in normalized or repo_slash in normalized.replace("\\", "/"):
                return True
    return False


def iter_prompts(session_root: Path, repo_root: str, cutoff):
    for transcript in session_root.rglob("*.jsonl"):
        session_id = ""
        try:
            items = []
            with transcript.open(encoding="utf-8-sig", errors="replace") as stream:
                for line_no, line in enumerate(stream, 1):
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict):
                        items.append((line_no, item))
            if not _belongs_to_repo(items, repo_root):
                continue
            for line_no, item in items:
                    payload = item.get("payload") or {}
                    if item.get("type") == "session_meta":
                        session_id = payload.get("session_id") or payload.get("id", "")
                        continue
                    if (item.get("type") != "event_msg"
                            or payload.get("type") != "user_message"):
                        continue
                    timestamp = item.get("timestamp", "")
                    timestamp_dt = parse_time(timestamp)
                    if cutoff and timestamp_dt and timestamp_dt < cutoff:
                        continue
                    prompt = payload.get("message", "")
                    if not isinstance(prompt, str) or not prompt.strip():
                        continue
                    prompt = prompt.strip()
                    if (prompt.startswith("<environment_context>")
                            and prompt.endswith("</environment_context>")):
                        continue
                    yield session_id or transcript.stem, line_no, timestamp, prompt
        except OSError:
            continue


def main():
    parser = argparse.ArgumentParser(description="Log Codex prompts from local sessions")
    parser.add_argument("--hours", type=int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    sessions = codex_home / "sessions"
    if not sessions.exists():
        print("[codex-log] No local Codex sessions found.", file=sys.stderr)
        return

    repo_path = Path(__file__).resolve().parent.parent
    log_dir = Path(os.environ.get("AI_LOG_DIR", repo_path / ".ai-log"))
    if not log_dir.is_absolute():
        log_dir = repo_path / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "session.jsonl"
    seen = logged_ids(log_dir)
    cutoff = None if args.all else datetime.now(timezone.utc) - timedelta(hours=max(args.hours, 0))
    repo_root = norm_path(str(repo_path))
    repo = git("remote", "get-url", "origin").split("/")[-1].removesuffix(".git")
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    commit = git("rev-parse", "--short", "HEAD")
    student = git("config", "user.email") or os.environ.get("USERNAME", "unknown")

    entries = []
    for session_id, line_no, ts, prompt in iter_prompts(sessions, repo_root, cutoff):
        entry_id = f"codex-{session_id}-{line_no}"
        if entry_id in seen:
            continue
        entries.append({
            "ts": ts or datetime.now(VN_TZ).isoformat(), "tool": "codex",
            "event": "UserPromptSubmit", "entry_id": entry_id,
            # Codex transcripts expose the provider but not the underlying
            # model identifier. Keep the client label rather than inventing
            # a specific LLM name.
            "session_id": session_id, "model": "codex_cli", "repo": repo,
            "branch": branch, "commit": commit, "student": student,
            "prompt": prompt[:1000], "response_summary": "",
        })
        seen.add(entry_id)

    if args.dry_run:
        print(f"[codex-log] Would log {len(entries)} prompt(s).")
        return
    with log_file.open("a", encoding="utf-8") as stream:
        for entry in entries:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[codex-log] Logged {len(entries)} prompt(s).", file=sys.stderr)


if __name__ == "__main__":
    main()
