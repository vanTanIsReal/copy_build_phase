import importlib.util
import json
from pathlib import Path

# Dynamically import submit_log script
script_path = Path(__file__).parent.parent / "scripts" / "submit_log.py"
spec = importlib.util.spec_from_file_location("submit_log", script_path)
submit_log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(submit_log)


def test_archive_deduplication_and_streaming(tmp_path, monkeypatch):
    archive_dir = tmp_path / "archive"
    monkeypatch.setattr(submit_log, "ARCHIVE_DIR", archive_dir)

    pending_file = tmp_path / "pending.jsonl"

    # Write pending entries including internal duplicates
    pending_lines = [
        json.dumps({"entry_id": "1", "data": "first"}),
        json.dumps({"entry_id": "2", "data": "second"}),
        json.dumps({"entry_id": "1", "data": "first_dup"}),  # duplicate in pending
    ]
    pending_file.write_text("\n".join(pending_lines) + "\n", encoding="utf-8")

    # Run archive on first pending batch
    submit_log._archive(pending_file)

    today_files = list(archive_dir.glob("*.jsonl"))
    assert len(today_files) == 1
    archive_file = today_files[0]

    lines = archive_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    entries = [json.loads(line) for line in lines]
    assert [e["entry_id"] for e in entries] == ["1", "2"]

    # Now create a second pending batch with one new entry and one existing entry
    pending_file_2 = tmp_path / "pending2.jsonl"
    pending_lines_2 = [
        json.dumps({"entry_id": "2", "data": "second_dup"}),  # already archived
        json.dumps({"entry_id": "3", "data": "third"}),  # new
    ]
    pending_file_2.write_text("\n".join(pending_lines_2) + "\n", encoding="utf-8")

    submit_log._archive(pending_file_2)

    lines_after = archive_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines_after) == 3
    entries_after = [json.loads(line) for line in lines_after]
    assert [e["entry_id"] for e in entries_after] == ["1", "2", "3"]
