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

VN_TZ = timezone(timedelta(hours=7))


def git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], text=True, stderr=subprocess.DEVNULL
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


def logged_ids(log_file: Path) -> set[str]:
    ids = set()
    if not log_file.exists():
        return ids
    for line in log_file.read_text(encoding="utf-8-sig").splitlines():
        try:
            entry_id = json.loads(line).get("entry_id")
            if entry_id:
                ids.add(entry_id)
        except json.JSONDecodeError:
            pass
    return ids


def iter_prompts(session_root: Path, repo_root: str, cutoff):
    for transcript in session_root.rglob("*.jsonl"):
        session_id = ""
        session_cwd = ""
        try:
            with transcript.open(encoding="utf-8") as stream:
                for line_no, line in enumerate(stream, 1):
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = item.get("payload") or {}
                    if item.get("type") == "session_meta":
                        session_id = payload.get("session_id", "")
                        session_cwd = norm_path(payload.get("cwd", ""))
                        continue
                    if session_cwd != repo_root:
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
                    yield session_id, line_no, timestamp, prompt.strip()
        except OSError:
            continue


def main():
    parser = argparse.ArgumentParser(description="Log Codex prompts from local sessions")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sessions = Path.home() / ".codex" / "sessions"
    if not sessions.exists():
        print("[codex-log] No local Codex sessions found.", file=sys.stderr)
        return

    log_dir = Path(os.environ.get("AI_LOG_DIR", ".ai-log"))
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "session.jsonl"
    seen = logged_ids(log_file)
    cutoff = None if args.all else datetime.now(timezone.utc) - timedelta(hours=args.hours)
    repo_root = norm_path(str(Path.cwd().resolve()))
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
            "event": "UserPrompt", "entry_id": entry_id,
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
