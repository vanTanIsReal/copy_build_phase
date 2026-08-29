"""Build one honest Evaluation Evidence report from available machine-readable artifacts."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "eval" / "results"
OUTPUT = ROOT / "eval" / "EVALUATION_EVIDENCE.md"


def load_json(name: str) -> dict[str, Any] | None:
    path = RESULTS / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def source_revision() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    )
    return commit, dirty


def junit_summary() -> dict[str, int] | None:
    path = RESULTS / "test-results.junit.xml"
    if not path.exists():
        return None
    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    fields = ("tests", "failures", "errors", "skipped")
    return {field: sum(int(suite.attrib.get(field, 0)) for suite in suites) for field in fields}


def status(value: bool | None) -> str:
    if value is None:
        return "PENDING"
    return "PASS" if value else "FAIL"


def fmt_percent(value: float | None) -> str:
    return "Pending" if value is None else f"{value * 100:.1f}%"


def build_report() -> str:
    commit, dirty = source_revision()
    coverage = load_json("coverage-latest.json")
    tests = junit_summary()
    acceptance = load_json("agent_acceptance_latest.json")
    tasks = load_json("task-extraction-latest.json")
    latency = load_json("latency-latest.json")
    staging_latency = load_json("latency-chat-staging-latest.json")
    memory = load_json("memory-harness-postgres-latest.json")
    realtime = load_json("realtime-load-staging-latest.json")
    browser = load_json("browser-e2e-staging-latest.json")
    lighthouse = load_json("lighthouse-staging-latest.json")
    calendar = load_json("calendar-oauth-staging-latest.json")
    feedback = load_json("user-feedback-latest.json")
    synthetic_feedback = load_json("user-feedback-synthetic-demo.json")

    coverage_percent = coverage.get("totals", {}).get("percent_covered") if coverage else None
    coverage_passed = coverage_percent >= 60 if coverage_percent is not None else None
    tests_passed = None
    if tests:
        tests_passed = tests["failures"] == 0 and tests["errors"] == 0
    acceptance_passed = acceptance.get("release_gate", {}).get("passed") if acceptance else None
    latency_passed = latency.get("passed") if latency else None
    feedback_status = feedback.get("status") if feedback else None
    feedback_ready = None if feedback_status in {None, "PENDING"} else feedback_status == "READY"
    memory_passed = memory.get("status") == "PASS" if memory else None
    websocket_passed = None
    load_passed = None
    if realtime:
        websocket_passed = realtime.get("ws_connections") == 5 and (
            realtime.get("websocket", {}).get("deliveries")
            == realtime.get("websocket", {}).get("expected_deliveries")
            and realtime.get("websocket", {}).get("expected_deliveries", 0) > 0
        )
        load_passed = realtime.get("load", {}).get("success_2xx") == realtime.get("load", {}).get("requests")
    browser_functional_passed = None
    browser_accessibility_passed = None
    if browser:
        browser_functional_passed = bool(
            browser.get("user_login", {}).get("passed")
            and browser.get("browser_chat", {}).get("passed")
            and browser.get("admin_login", {}).get("passed")
            and all(route.get("http_status") == 200 for route in browser.get("user_routes", []))
            and all(route.get("http_status") == 200 for route in browser.get("admin_routes", []))
        )
        browser_accessibility_passed = not any(
            route.get("serious_or_critical", 0) > 0
            for route in browser.get("user_routes", []) + browser.get("admin_routes", [])
        )
    lighthouse_passed = None
    if lighthouse:
        lighthouse_passed = all(
            surface.get(check) == "PASS"
            for surface in (lighthouse.get("user", {}), lighthouse.get("admin", {}))
            for check in ("performance_status", "accessibility_status", "lcp_status", "cls_status")
        )
    calendar_ready = calendar.get("status") == "PASS" if calendar else None

    test_result = "Pending"
    if tests:
        passed_count = tests["tests"] - tests["failures"] - tests["errors"] - tests["skipped"]
        test_result = f"{passed_count}/{tests['tests']} passed, {tests['skipped']} skipped"

    task_f1 = tasks.get("title_f1") if tasks else None
    date_accuracy = tasks.get("date_accuracy") if tasks else None
    acceptance_case_rate = acceptance.get("metrics", {}).get("case_pass_rate") if acceptance else None
    p95 = latency.get("metrics", {}).get("p95_ms") if latency else None
    feedback_rating = feedback.get("rating_mean") if feedback else None
    staging_p95 = staging_latency.get("total", {}).get("p95_ms") if staging_latency else None
    staging_success = staging_latency.get("success_count") if staging_latency else None
    staging_requests = staging_latency.get("request_count") if staging_latency else None
    staging_chat_passed = (
        staging_success == staging_requests and staging_p95 <= 5000
        if staging_requests is not None and staging_p95 is not None
        else None
    )
    load_success = realtime.get("load", {}).get("success_2xx") if realtime else None
    load_requests = realtime.get("load", {}).get("requests") if realtime else None

    failure_reasons: list[str] = []
    if acceptance_passed is False and acceptance:
        failed_checks = acceptance.get("release_gate", {}).get("checks", {})
        failed_details = []
        for name, check in failed_checks.items():
            if not check.get("passed"):
                failed_details.append(
                    f"`{name}` {fmt_percent(check.get('value'))} so với ngưỡng "
                    f"{fmt_percent(check.get('threshold'))}"
                )
        failure_reasons.append(
            f"**Formal Agent acceptance = FAIL:** chỉ {fmt_percent(acceptance_case_rate)} số case đạt; "
            + "; ".join(failed_details)
            + "."
        )
    if websocket_passed is False and realtime:
        websocket = realtime.get("websocket", {})
        failure_reasons.append(
            f"**Staging WebSocket = FAIL:** chỉ mở được {realtime.get('ws_connections', 0)}/5 kết nối. "
            f"Handshake trả về `{websocket.get('handshake_error', 'unknown error')}`, nên không thể đo độ trễ "
            "phân phối hoặc quan sát event reminder qua WebSocket."
        )
    if load_passed is False and realtime:
        status_counts = json.dumps(realtime.get("load", {}).get("status_counts", {}), sort_keys=True)
        failure_reasons.append(
            f"**Staging HTTP load = FAIL:** chỉ {load_success}/{load_requests} request trả về 2xx; "
            f"phân bố status là `{status_counts}`. 15 phản hồi HTTP 429 cho thấy đã chạm rate limit; đây không "
            "phải lỗi sập 5xx, nhưng vẫn không đạt gate yêu cầu toàn bộ request trả về 2xx."
        )
    if browser_accessibility_passed is False and browser:
        user_serious = sum(route.get("serious_or_critical", 0) for route in browser.get("user_routes", []))
        admin_serious = sum(route.get("serious_or_critical", 0) for route in browser.get("admin_routes", []))
        violation_kinds = sorted(
            {
                item.split(":", 1)[0]
                for route in browser.get("user_routes", []) + browser.get("admin_routes", [])
                for item in route.get("violation_ids", [])
                if item
            }
        )
        failure_reasons.append(
            f"**Browser accessibility = FAIL:** gate yêu cầu không có lỗi serious/critical, nhưng ghi nhận "
            f"{user_serious} lỗi theo route user và {admin_serious} lỗi theo route admin. Các nhóm lỗi gồm "
            f"`{', '.join(violation_kinds)}`; tổng theo route có thể lặp lại cùng một nhóm lỗi."
        )
    if lighthouse_passed is False and lighthouse:
        user_lh = lighthouse.get("user", {})
        admin_lh = lighthouse.get("admin", {})
        failure_reasons.append(
            "**Lighthouse aggregate = FAIL:** performance user "
            f"{user_lh.get('performance')} < 80 và LCP user {user_lh.get('lcp_ms')} ms > 2500 ms; "
            f"accessibility admin {admin_lh.get('accessibility')} < 90 và LCP admin "
            f"{admin_lh.get('lcp_ms')} ms > 2500 ms. Accessibility user, performance admin và hai phép đo "
            "CLS đều đạt, nhưng gate tổng yêu cầu tất cả phép kiểm tra cùng đạt."
        )
    if calendar_ready is False and calendar:
        failure_reasons.append(
            "**Google Calendar OAuth = FAIL/PARTIAL:** cấu hình runtime tạo thành công URL cấp quyền Google "
            f"và callback origin khớp staging, nhưng `currently_connected` là "
            f"`{str(calendar.get('currently_connected', False)).lower()}` và consent tương tác là "
            f"`{calendar.get('interactive_google_consent', 'NOT_RUN')}`. Chưa có authorization code/token "
            "exchange, nên chưa thể đánh dấu truy cập Calendar riêng tư là PASS."
        )
    if feedback_ready is not True:
        real_participants = feedback.get("participant_count", 0) if feedback else 0
        minimum_participants = feedback.get("minimum_participants", 5) if feedback else 5
        synthetic_participants = synthetic_feedback.get("participant_count", 0) if synthetic_feedback else 0
        failure_reasons.append(
            f"**User feedback = PENDING:** mới ghi nhận {real_participants}/{minimum_participants} người dùng "
            f"thật bắt buộc. {synthetic_participants} phản hồi được tạo là dữ liệu kiểm thử hư cấu đã gắn nhãn "
            "rõ ràng và không được tính vào bằng chứng phát hành."
        )
    failure_reason_text = "\n\n".join(f"- {reason}" for reason in failure_reasons)

    generated_at = datetime.now(UTC).isoformat()
    return f"""# Evaluation Evidence — Orbit

Generated at `{generated_at}` from source revision `{commit}`
{"with uncommitted evaluation changes" if dirty else "with a clean working tree"}.

This report never converts missing evidence into a passing score. `PENDING` means the runner or
protocol exists but no current result artifact is available.

## 1. Release evidence summary

| Evidence | Result | Gate | Status |
|---|---:|---:|---|
| Automated tests | {test_result} | No failures/errors | {status(tests_passed)} |
| Source coverage | {f"{coverage_percent:.1f}%" if coverage_percent is not None else "Pending"} | >=60% | {status(coverage_passed)} |
| Formal Agent acceptance | {fmt_percent(acceptance_case_rate)} case pass | Dataset gates | {status(acceptance_passed)} |
| Task title F1 | {fmt_percent(task_f1)} | >=70% | {status(task_f1 >= 0.70 if task_f1 is not None else None)} |
| Deadline accuracy | {fmt_percent(date_accuracy)} | >=70% | {status(date_accuracy >= 0.70 if date_accuracy is not None else None)} |
| API latency P95 | {f"{p95:.1f} ms" if p95 is not None else "Pending"} | Configured runner gate | {status(latency_passed)} |
| Staging chat | {f"{staging_success}/{staging_requests}; P95 {staging_p95:.1f} ms" if staging_p95 is not None else "Pending"} | All complete; P95 <=5000 ms | {status(staging_chat_passed)} |
| PostgreSQL memory harness | {f"{memory.get('passed', 0)}/{memory.get('tests', 0)} passed" if memory else "Pending"} | No failures/errors | {status(memory_passed)} |
| Staging WebSocket | {f"{realtime.get('ws_connections', 0)}/5 connected" if realtime else "Pending"} | 5 connections and all deliveries | {status(websocket_passed)} |
| Staging HTTP load | {f"{load_success}/{load_requests} 2xx" if realtime else "Pending"} | All requests return 2xx | {status(load_passed)} |
| Browser functional E2E | {"User/admin login, chat, and routes" if browser else "Pending"} | All functional checks pass | {status(browser_functional_passed)} |
| Browser accessibility | {"No serious/critical findings" if browser_accessibility_passed else "Serious/critical findings remain" if browser else "Pending"} | Zero serious/critical findings | {status(browser_accessibility_passed)} |
| Lighthouse aggregate | {"Both user/admin surfaces" if lighthouse else "Pending"} | All configured web gates pass | {status(lighthouse_passed)} |
| Google Calendar OAuth | {calendar.get("status", "Pending") if calendar else "Pending"} | Interactive consent and token exchange | {status(calendar_ready)} |
| User feedback | {f"{feedback_rating:.2f}/5" if feedback_rating is not None else "Pending"} | >=5 participants | {status(feedback_ready)} |

## 2. Vì sao từng mục là FAIL hoặc PENDING

Kết luận phát hành tổng thể: **FAIL** vì một hoặc nhiều gate bắt buộc dưới đây chưa đạt.

{failure_reason_text or "Không có kết quả FAIL hoặc PENDING."}

## 3. Current measured AI quality

- Formal acceptance: `{acceptance.get("run_at", "unknown") if acceptance else "Pending"}` using
  `{acceptance.get("provider", "unknown") if acceptance else "unknown"}/{acceptance.get("model", "unknown") if acceptance else "unknown"}`.
- Task extraction: `{tasks.get("case_count", 0) if tasks else 0}` cases; title precision
  `{fmt_percent(tasks.get("title_precision") if tasks else None)}`, recall
  `{fmt_percent(tasks.get("title_recall") if tasks else None)}`, F1 `{fmt_percent(task_f1)}`.
- Missing or failed gates remain release risks even when deterministic unit tests pass.

## 4. Synthetic feedback (not release evidence)

The synthetic demo contains `{synthetic_feedback.get("participant_count", 0) if synthetic_feedback else 0}` fictional
participants and is labeled `INSUFFICIENT_DATA`. It is useful only to exercise the reporting pipeline and is never
substituted for the real feedback row above.

## 5. Reproducible commands

```powershell
python scripts/run_coverage.py
python scripts/benchmark_api_latency.py --base-url http://127.0.0.1:8000 --endpoint /health
python scripts/eval_user_agent.py
python scripts/eval_extract_tasks.py
python scripts/summarize_user_feedback.py
python scripts/generate_evaluation_evidence.py
```

## 6. Traceability and evidence locations

- Requirement-to-test-to-code map: [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md)
- Manual scenarios: [`../MANUAL_TEST_CASES.md`](../MANUAL_TEST_CASES.md)
- Screenshot/video evidence: [`../Deliverables/evidence/`](../Deliverables/evidence/)
- Formal acceptance: [`results/agent_acceptance_latest.md`](results/agent_acceptance_latest.md)
- PostgreSQL memory harness: [`results/memory-harness-postgres-latest.md`](results/memory-harness-postgres-latest.md)
- Staging realtime/load: [`results/realtime-load-staging-latest.md`](results/realtime-load-staging-latest.md)
- Browser E2E/accessibility: [`results/browser-e2e-staging-latest.md`](results/browser-e2e-staging-latest.md)
- Lighthouse: [`results/lighthouse-staging-latest.md`](results/lighthouse-staging-latest.md)
- Calendar OAuth: [`results/calendar-oauth-staging-latest.md`](results/calendar-oauth-staging-latest.md)
- Synthetic feedback demo: [`results/user-feedback-synthetic-demo.md`](results/user-feedback-synthetic-demo.md)
- Evaluation protocols and commands: [`README.md`](README.md)

## 7. Evidence still requiring human/external execution

- User satisfaction requires real anonymized participants; no synthetic rating is accepted.
- Calendar token exchange requires a user to complete Google's interactive consent flow.
- INP requires real-user or controlled interaction data; navigation-only Lighthouse does not measure it.
- Coverage/JUnit artifacts must be regenerated after material source changes.
"""


def main() -> int:
    OUTPUT.write_text(build_report(), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
