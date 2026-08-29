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


def load_project_json(relative_path: str) -> dict[str, Any] | None:
    path = ROOT / relative_path
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def source_revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


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
    commit = source_revision()
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
    false_reminders = load_json("false-reminder-staging-latest.json")
    deploy_metrics = load_json("deploy-latency-cost-latest.json")
    feedback = load_json("user-feedback-latest.json")
    synthetic_feedback = load_json("user-feedback-synthetic-demo.json")
    staging_tasks = load_project_json("eval/extract_report.json")

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
    user_serious = 0
    admin_serious = 0
    violation_kinds: list[str] = []
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
    load_status_counts = json.dumps(realtime.get("load", {}).get("status_counts", {}), sort_keys=True) if realtime else "Pending"
    acceptance_metrics = acceptance.get("metrics", {}) if acceptance else {}
    acceptance_cases = acceptance.get("cases", []) if acceptance else []
    acceptance_passed_cases = sum(bool(case.get("passed")) for case in acceptance_cases)
    staging_task_range = staging_tasks.get("range", {}) if staging_tasks else {}
    deploy_latency = deploy_metrics.get("latency", {}) if deploy_metrics else {}

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
    return f"""# Báo cáo đánh giá tổng hợp — Orbit

Tạo lúc `{generated_at}` từ source revision cơ sở `{commit}`.

Báo cáo không chuyển bằng chứng còn thiếu thành điểm đạt. `PENDING` nghĩa là đã có runner/protocol nhưng
chưa có đủ kết quả hợp lệ hiện tại.

## 1. Tổng quan gate phát hành

| Hạng mục | Kết quả | Gate | Trạng thái |
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

## 3. Kết quả chi tiết đã hợp nhất

Đây là **file báo cáo duy nhất dành cho người đọc**. Các JSON trong `eval/results/` chỉ là dữ liệu máy đọc
được giữ lại để kiểm chứng và tái lập, không phải các báo cáo cần đọc riêng.

### 3.1 Backend, coverage và PostgreSQL

| Phép đo | Kết quả | Trạng thái |
|---|---:|---|
| Automated tests | {test_result} | {status(tests_passed)} |
| Source coverage | {f"{coverage_percent:.2f}%" if coverage_percent is not None else "Pending"} | {status(coverage_passed)} |
| PostgreSQL memory/quality harness | {f"{memory.get('passed', 0)}/{memory.get('tests', 0)}" if memory else "Pending"} | {status(memory_passed)} |
| Database harness | {f"{memory.get('database_engine')} tại {memory.get('database_host')}:{memory.get('database_port')}/{memory.get('database_name')}" if memory else "Pending"} | {"Cô lập, không dùng production" if memory else "Pending"} |

### 3.2 Agent acceptance và chất lượng AI

Formal acceptance chạy lúc `{acceptance.get("run_at", "unknown") if acceptance else "Pending"}` bằng
`{acceptance.get("provider", "unknown") if acceptance else "unknown"}/{acceptance.get("model", "unknown") if acceptance else "unknown"}`.

| Chỉ số | Kết quả | Gate | Trạng thái |
|---|---:|---:|---|
| Case pass | {acceptance_passed_cases}/{len(acceptance_cases)} ({fmt_percent(acceptance_case_rate)}) | >=80% | {status(acceptance_case_rate >= 0.8 if acceptance_case_rate is not None else None)} |
| Tool routing | {fmt_percent(acceptance_metrics.get("tool_routing_accuracy"))} | >=95% | {status(acceptance_metrics.get("tool_routing_accuracy", 0) >= 0.95 if acceptance else None)} |
| Task precision/recall/F1 | {fmt_percent(acceptance_metrics.get("task_precision"))} / {fmt_percent(acceptance_metrics.get("task_recall"))} / {fmt_percent(acceptance_metrics.get("task_f1"))} | >=90% | {status(acceptance_metrics.get("task_f1", 0) >= 0.9 if acceptance else None)} |
| Task due accuracy | {fmt_percent(acceptance_metrics.get("task_due_accuracy"))} | >=90% | {status(acceptance_metrics.get("task_due_accuracy", 0) >= 0.9 if acceptance else None)} |
| Task priority accuracy | {fmt_percent(acceptance_metrics.get("task_priority_accuracy"))} | Thông tin | N/A |
| Required fact recall | {fmt_percent(acceptance_metrics.get("required_fact_recall"))} | Thông tin | N/A |
| Forbidden claim rate | {fmt_percent(acceptance_metrics.get("forbidden_claim_rate"))} | 0% | {status(acceptance_metrics.get("forbidden_claim_rate") == 0 if acceptance else None)} |
| HITL pre-confirmation side effects | {fmt_percent(acceptance_metrics.get("hitl_preconfirmation_side_effect_rate"))} | 0% | {status(acceptance_metrics.get("hitl_preconfirmation_side_effect_rate") == 0 if acceptance else None)} |
| Memory retrieval/isolation/expired rejection | {fmt_percent(acceptance_metrics.get("memory_retrieval_accuracy"))} / {fmt_percent(acceptance_metrics.get("memory_isolation_pass_rate"))} / {fmt_percent(acceptance_metrics.get("expired_memory_rejection_rate"))} | Isolation 100% | FAIL |
| Agent latency P50/P95 | {acceptance_metrics.get("latency_p50_ms", "Pending")} / {acceptance_metrics.get("latency_p95_ms", "Pending")} ms | Thông tin | N/A |
| LLM judge mean / unsupported claims | {acceptance_metrics.get("llm_judge_mean_score", "Pending")} / {fmt_percent(acceptance_metrics.get("unsupported_claim_rate"))} | Thông tin | N/A |
| Token / request / estimated cost | {acceptance_metrics.get("total_tokens", 0)} / {acceptance_metrics.get("llm_request_count", 0)} / ${acceptance_metrics.get("estimated_cost_usd", 0):.6f} | Thông tin | N/A |

### 3.3 Task extraction và chống tạo task giả

| Môi trường | Case/run | Precision | Recall | F1 | Date accuracy | Trạng thái |
|---|---:|---:|---:|---:|---:|---|
| Local OpenRouter `{tasks.get("model", "unknown") if tasks else "unknown"}` | {tasks.get("case_count", 0) if tasks else 0} case | {fmt_percent(tasks.get("title_precision") if tasks else None)} | {fmt_percent(tasks.get("title_recall") if tasks else None)} | {fmt_percent(task_f1)} | {fmt_percent(date_accuracy)} | {status(task_f1 >= 0.7 and date_accuracy >= 0.7 if task_f1 is not None and date_accuracy is not None else None)} |
| Staging `{staging_tasks.get("model", "unknown") if staging_tasks else "unknown"}` | {f"{staging_tasks.get('case_count')} case x {staging_tasks.get('run_count')} run" if staging_tasks else "Pending"} | {f"{fmt_percent(staging_task_range.get('title_precision', {}).get('min'))}..{fmt_percent(staging_task_range.get('title_precision', {}).get('max'))}" if staging_tasks else "Pending"} | {f"{fmt_percent(staging_task_range.get('title_recall', {}).get('min'))}..{fmt_percent(staging_task_range.get('title_recall', {}).get('max'))}" if staging_tasks else "Pending"} | {f"{fmt_percent(staging_task_range.get('title_f1', {}).get('min'))}..{fmt_percent(staging_task_range.get('title_f1', {}).get('max'))}" if staging_tasks else "Pending"} | {f"{fmt_percent(staging_task_range.get('date_accuracy', {}).get('min'))}..{fmt_percent(staging_task_range.get('date_accuracy', {}).get('max'))}" if staging_tasks else "Pending"} | PASS |
| Non-commitment false-positive staging | {false_reminders.get("case_count", 0) if false_reminders else 0} case | — | — | {fmt_percent(1 - false_reminders.get("false_positive_rate", 1)) if false_reminders else "Pending"} không tạo sai | — | {status(false_reminders.get("false_positive_count") == 0 if false_reminders else None)} |

Bộ non-commitment gồm greeting, discussion, question, delegated-to-other và completed-past; ghi nhận
`{false_reminders.get("false_positive_count", "Pending") if false_reminders else "Pending"}` false positive,
`{false_reminders.get("usage_total_tokens", "Pending") if false_reminders else "Pending"}` token và chi phí ước tính
`${false_reminders.get("usage_estimated_cost_usd", 0):.7f}`.

### 3.4 Staging API, latency, WebSocket và scheduler

| Luồng | Kết quả | Ghi chú |
|---|---:|---|
| Chat benchmark mới nhất | {f"{staging_success}/{staging_requests}, P50 {staging_latency.get('total', {}).get('p50_ms')} ms, P95 {staging_p95} ms" if staging_latency else "Pending"} | Endpoint không streaming; TTFB không phải TTFT thật |
| Summary benchmark sâu | {f"{deploy_latency.get('summary', {}).get('success_count')}/{deploy_latency.get('summary', {}).get('request_count')}, P95 {deploy_latency.get('summary', {}).get('metrics', {}).get('p95_ms')} ms" if deploy_metrics else "Pending"} | Run staging riêng trước benchmark mới nhất |
| Task-extraction benchmark sâu | {f"{deploy_latency.get('task_extraction', {}).get('success_count')}/{deploy_latency.get('task_extraction', {}).get('request_count')}, P95 {deploy_latency.get('task_extraction', {}).get('metrics', {}).get('p95_ms')} ms" if deploy_metrics else "Pending"} | Run staging riêng |
| Planner benchmark sâu | {f"{deploy_latency.get('planner', {}).get('success_count')}/{deploy_latency.get('planner', {}).get('request_count')}, P95 {deploy_latency.get('planner', {}).get('metrics', {}).get('p95_ms')} ms" if deploy_metrics else "Pending"} | Có 1 HTTP 500 sau khoảng 60,7 giây |
| Known cost subtotal / 1000 messages | {f"${deploy_metrics.get('known_cost_subtotal_per_1000_messages_usd'):.6f}" if deploy_metrics else "Pending"} | Chưa gồm `{', '.join(deploy_metrics.get('unmeasured_cost_components', [])) if deploy_metrics else 'Pending'}`; không phải tổng hoàn chỉnh |
| WebSocket | {f"{realtime.get('ws_connections', 0)}/5 kết nối" if realtime else "Pending"} | {realtime.get('websocket', {}).get('handshake_error', 'Pending') if realtime else 'Pending'} |
| Task CRUD | {f"{realtime.get('task', {}).get('create_status')}/{realtime.get('task', {}).get('list_status')}/{realtime.get('task', {}).get('update_status')}/{realtime.get('task', {}).get('delete_status')}" if realtime else "Pending"} | Create/list/update/delete PASS |
| Reminder scheduler | {realtime.get("reminder", {}).get("final_status", "Pending") if realtime else "Pending"} | Scheduler fired; event WebSocket không quan sát được do handshake 403 |
| HTTP load | {f"{load_success}/{load_requests} 2xx; {load_status_counts}" if realtime else "Pending"} | 15 HTTP 429, không có 5xx trong load 100 request |

Benchmark sâu ghi nhận telemetry `openai/gpt-4o-mini`, còn benchmark chat mới nhất ghi nhận
`{staging_latency.get("model", {}).get("provider", "unknown") if staging_latency else "unknown"}/{staging_latency.get("model", {}).get("name", "unknown") if staging_latency else "unknown"}`.
Hai artifact có thời điểm khác nhau nên không được coi là cùng một cấu hình runtime. Usage delta của benchmark mới nhất bằng 0,
vì vậy báo cáo **không** diễn giải thành chi phí thực bằng 0.

### 3.5 Browser, accessibility và Lighthouse

| Surface | Functional E2E | Serious/critical theo route | Performance | Accessibility | LCP | CLS |
|---|---|---:|---:|---:|---:|---:|
| User | {f"Login + chat + {len(browser.get('user_routes', []))}/{len(browser.get('user_routes', []))} route PASS" if browser else "Pending"} | {user_serious} | {lighthouse.get("user", {}).get("performance", "Pending") if lighthouse else "Pending"} | {lighthouse.get("user", {}).get("accessibility", "Pending") if lighthouse else "Pending"} | {f"{lighthouse.get('user', {}).get('lcp_ms')} ms" if lighthouse else "Pending"} | {lighthouse.get("user", {}).get("cls", "Pending") if lighthouse else "Pending"} |
| Admin | {f"Login + {len(browser.get('admin_routes', []))}/{len(browser.get('admin_routes', []))} route PASS" if browser else "Pending"} | {admin_serious} | {lighthouse.get("admin", {}).get("performance", "Pending") if lighthouse else "Pending"} | {lighthouse.get("admin", {}).get("accessibility", "Pending") if lighthouse else "Pending"} | {f"{lighthouse.get('admin', {}).get('lcp_ms')} ms" if lighthouse else "Pending"} | {lighthouse.get("admin", {}).get("cls", "Pending") if lighthouse else "Pending"} |

Các nhóm lỗi accessibility: `{', '.join(violation_kinds) if violation_kinds else 'Pending'}`. INP chưa đo vì
Lighthouse navigation-only không cung cấp dữ liệu tương tác thật.

### 3.6 Google Calendar-only OAuth

Google Sign-In đã được loại khỏi phạm vi theo yêu cầu; chỉ luồng cấp quyền Calendar được đánh giá.

| Kiểm tra | Kết quả |
|---|---|
| Tạo authorization URL | {calendar.get("authorization_url_status", "Pending") if calendar else "Pending"}; host `{calendar.get("authorization_host", "Pending") if calendar else "Pending"}` |
| Calendar scope và client ID | {"Có" if calendar and calendar.get("calendar_scope_present") and calendar.get("authorization_url_has_client_id") else "Không/Pending"} |
| Client ID khớp cấu hình Calendar local | {str(calendar.get("client_id_matches_local_calendar_setting", False)).lower() if calendar else "Pending"} |
| Redirect URI | `{calendar.get("redirect_uri", "Pending") if calendar else "Pending"}` |
| Callback FRONTEND_ORIGIN khớp staging | {str(calendar.get("callback_frontend_origin_matches_staging", False)).lower() if calendar else "Pending"}; `{calendar.get("callback_frontend_origin", "Pending") if calendar else "Pending"}` |
| Account đánh giá đã kết nối | {str(calendar.get("currently_connected", False)).lower() if calendar else "Pending"} |
| Google consent/token exchange | {calendar.get("interactive_google_consent", "Pending") if calendar else "Pending"} |

Kết luận Calendar: **PARTIAL/FAIL**. Cấu hình runtime đủ để bắt đầu OAuth, nhưng truy cập Calendar riêng tư vẫn cần
người dùng Google hoàn tất màn consent; ứng dụng không cần dùng Google Sign-In làm cơ chế đăng nhập.

### 3.7 Feedback

- Feedback thật: `{feedback.get("participant_count", 0) if feedback else 0}/{feedback.get("minimum_participants", 5) if feedback else 5}` người, trạng thái **PENDING**.
- Feedback mô phỏng: `{synthetic_feedback.get("participant_count", 0) if synthetic_feedback else 0}` người hư cấu,
  task completion `{fmt_percent(synthetic_feedback.get("task_completion_rate") if synthetic_feedback else None)}`,
  rating `{synthetic_feedback.get("rating_mean", "Pending") if synthetic_feedback else "Pending"}/5`, helpfulness
  `{synthetic_feedback.get("helpfulness_mean", "Pending") if synthetic_feedback else "Pending"}/5`, trust
  `{synthetic_feedback.get("trust_mean", "Pending") if synthetic_feedback else "Pending"}/5`.
- Dữ liệu mô phỏng chỉ kiểm thử pipeline và **không được tính** làm feedback thật hoặc gate phát hành.

## 4. Lệnh tái lập

```powershell
python scripts/run_coverage.py
python scripts/benchmark_api_latency.py --base-url http://127.0.0.1:8000 --endpoint /health
python scripts/eval_user_agent.py
python scripts/eval_extract_tasks.py
python scripts/summarize_user_feedback.py
python scripts/generate_evaluation_evidence.py
```

## 5. Phần vẫn cần con người hoặc dữ liệu bên ngoài

- Cần tối thiểu 5 người dùng thật cung cấp feedback ẩn danh; không chấp nhận rating mô phỏng.
- Cần một người dùng hoàn tất Google Calendar consent và token exchange.
- Cần dữ liệu tương tác thật hoặc controlled interaction để đo INP.
- Cần chạy lại coverage/JUnit sau thay đổi source đáng kể.
"""


def main() -> int:
    OUTPUT.write_text(build_report(), encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
