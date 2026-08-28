# Báo cáo đánh giá code `deploy` và hướng dẫn triển khai đánh giá

## 1. Phạm vi và kết luận

Báo cáo này đánh giá cây mã nguồn mới nhất của `origin/deploy` tại commit
`6c8b489f51e683ccd4218956989df1d5a696b43c` (`fix: make user app standalone for Vercel`). Nhánh
đang làm việc là `hau` tại commit `f37cce4a987089e0c2d39fb04ac23aa83cd3c966`; hai commit có cùng
tree hash nên nội dung source được đánh giá giống hệt `origin/deploy`.

Thời điểm đánh giá: **2026-08-28**, múi giờ `Asia/Bangkok` (UTC+7).

Kết luận release: **HOLD / CHƯA ĐỦ ĐIỀU KIỆN PHÁT HÀNH**.

- Nền tảng kỹ thuật đạt baseline: toàn bộ 410 test pass, coverage vượt gate, migration PostgreSQL
  từ database trắng pass, hai frontend build pass, static check và dependency audit pass.
- Chất lượng AI chưa đạt release gate: RAGAS fail ở `faithfulness` và `answer_relevancy`.
- Formal Agent mới chỉ pass 5/17 case; task extraction đạt gate của runner nhưng chưa đạt precision/F1
  theo release gate sản phẩm trong `metric.md`.
- Chưa có dữ liệu phản hồi người dùng thật và chưa đo latency của endpoint chat/model thật.

Không có source, test, script hay cấu hình nào được sửa trong quá trình đánh giá. Artifact máy đầy đủ
được ghi tại `D:\deploy\orbit-eval-artifacts-20260828`; các file `latest` trong `eval/results/` và báo
cáo tổng hợp được thay bằng kết quả mới theo yêu cầu, còn các report/rerun lịch sử đã được loại bỏ.

## 2. Môi trường đánh giá

| Thành phần | Giá trị |
|---|---|
| Hệ điều hành | Windows |
| Python | 3.13.14 |
| Node.js | 22.12.0 |
| npm | 10.9.0 |
| PostgreSQL | 17.10, local isolated cluster |
| Database test | `orbit_agent_eval_test` |
| PostgreSQL endpoint | `127.0.0.1:55432` |
| RAGAS application/evaluator | `openai/gpt-5.6-luna` qua OpenRouter |
| RAGAS embedding | `openai/text-embedding-3-small` |

Database PostgreSQL trên là database test riêng, chỉ bind localhost và không dùng chung database
`orbit` trong `.env`. Dữ liệu trong database này có thể bị reset bởi runner đánh giá.

## 3. Kết quả đo mới

### 3.1 Tổng hợp release gate

| Hạng mục | Kết quả | Gate | Trạng thái |
|---|---:|---:|---|
| Backend regression | 410/410 pass | Không failure/error | **PASS** |
| Coverage `src` có branch | 66,71% | >= 60% | **PASS** |
| PostgreSQL checkpoint reconnect | 1/1 pass | Phải pass trên PostgreSQL thật | **PASS** |
| Alembic fresh upgrade | Đến `20260826_25` | Upgrade từ DB trắng không lỗi | **PASS** |
| Ruff | 0 lỗi | 0 lỗi | **PASS** |
| Python dependency consistency | Không có broken requirement | 0 lỗi | **PASS** |
| User frontend build | Thành công | Build thành công | **PASS** |
| Admin frontend build | Thành công | Build thành công | **PASS** |
| npm production audit, user | 0 vulnerability | Không high/critical | **PASS** |
| npm production audit, admin | 0 vulnerability | Không high/critical | **PASS** |
| RAGAS grounding | 2/4 metric đạt | Tất cả metric phải đạt | **FAIL** |
| `/health` latency P95 | 21,238 ms | <= 5.000 ms, 100% HTTP 200 | **PASS** |
| `/ready` latency P95 | 1.185,869 ms | <= 5.000 ms, 100% HTTP 200 | **PASS** |
| Formal user-agent acceptance | 5/17 pass (29,4%) | >= 80% và các gate thành phần | **FAIL** |
| Task title precision | 83,3% | >= 90% theo `metric.md` | **FAIL** |
| Task title recall | 83,3% | >= 80% theo `metric.md` | **PASS** |
| Task title F1 | 83,3% | >= 85% theo `metric.md` | **FAIL** |
| Task deadline accuracy | 100% (8/8) | >= 90% theo `metric.md` | **PASS** |
| User feedback | 0 participant | >= 5 participant | **PENDING** |
| Chat/model latency | Chưa đo | P95 < 5 giây | **PENDING** |

### 3.2 Backend và coverage

Lệnh full suite sạch, có bật PostgreSQL test và `SelectorEventLoop` trên Windows, cho kết quả:

```text
410 passed, 64 warnings in 380.37s
Required test coverage of 60% reached. Total coverage: 66.71%
```

Coverage gồm 6.812 statement, 4.919 line được cover, 1.893 line chưa cover; 790/1.746 branch được
cover. Coverage tổng đạt gate nhưng biên an toàn chỉ cao hơn gate 6,71 điểm phần trăm.

Các vùng có rủi ro coverage đáng chú ý:

| Vùng | Coverage | Nhận định |
|---|---:|---|
| `src/services/conversation_service.py` | 0,0% | Service production không có bằng chứng trực tiếp |
| `src/services/people_intelligence_service.py` | 16,6% | Feature mới, xử lý directory/private note nhưng gần như chưa test |
| `src/agents/tools/people_tool.py` | 39,5% | Tool mới chưa được test đầy đủ theo nhánh lỗi/quyền |
| `src/services/chat_service.py` | 40,6% | Luồng chat quan trọng còn nhiều nhánh chưa cover |
| `src/api/task_routes.py` | 44,4% | Các nhánh workspace/calendar sync còn thiếu test |
| `src/services/workspace_service.py` | 44,8% | Ranh giới phân quyền workspace cần coverage cao hơn |
| `src/api/calendar_routes.py` | 46,0% | OAuth/error path chưa được cover đầy đủ |
| `src/api/chat_routes.py` | 48,3% | Request boundary quan trọng còn coverage thấp |

64 warning hiện tại chủ yếu là deprecation từ `google-genai`, Starlette và adapter datetime của
`aiosqlite`. Warning chưa làm fail release gate nhưng cần theo dõi trước khi nâng dependency.

### 3.3 PostgreSQL và migration

Các bằng chứng đã chạy trên PostgreSQL 17.10 thật:

- `AsyncPostgresSaver` ghi checkpoint, đóng pool, mở pool mới và đọc lại checkpoint thành công.
- Alembic nâng một database trắng qua toàn bộ revision đến `20260826_25` thành công.
- Backend `/ready` trả 100/100 HTTP 200 sau migration.

Trên Windows, test psycopg async phải chạy với `SelectorEventLoop`. Nếu chạy pytest trực tiếp bằng
event loop mặc định, test sẽ timeout với thông báo psycopg không hỗ trợ `ProactorEventLoop`; đây là
lỗi cách khởi chạy môi trường Windows, không phải lỗi kết nối PostgreSQL.

### 3.4 Frontend, dependency và bundle

- User app: 728 module được transform, build thành công trong khoảng 2,93 giây.
- Admin app: 52 module được transform, build thành công trong khoảng 1,56 giây.
- `npm audit --omit=dev --audit-level=high`: 0 vulnerability cho cả hai app.
- `pip check`: không có broken requirement.
- `ruff check src tests scripts`: pass.

User build có cảnh báo chunk vượt 500 kB. Chunk `CalendarPage` là **1.058,80 kB** sau minify
(136,43 kB gzip). Đây không phải lỗi chức năng nhưng là rủi ro tải/parse JavaScript trên thiết bị yếu;
nên đo Web Vitals trên staging và cân nhắc code splitting theo route/thư viện lịch.

### 3.5 RAGAS mới

Dataset: 5 case summary tổng hợp, không chứa dữ liệu production.

| Metric | Điểm | Gate | Trạng thái |
|---|---:|---:|---|
| Faithfulness | 0,666667 | >= 0,70 | **FAIL** |
| Answer relevancy | 0,405250 | >= 0,70 | **FAIL** |
| Context precision | 0,844444 | >= 0,60 | **PASS** |
| Context recall | 1,000000 | >= 0,60 | **PASS** |

Kết luận: model giữ được đầy đủ context cần thiết và context retrieval có precision tốt, nhưng câu
trả lời chưa vượt gate về bám nguồn và độ liên quan theo grader. Không được lấy trung bình bốn metric
để ghi đè hai gate fail.

Có một sai lệch trong thiết kế benchmark cần ghi nhận khi diễn giải kết quả: prompt production trong
`summarize_tool.py` bắt model đổi ngày tương đối thành ngày tuyệt đối theo thời điểm chạy, trong khi
dataset/reference RAGAS vẫn giữ các cụm như “ngày mai” và “thứ Sáu tuần sau”. Current context đưa cho
grader không chứa timestamp đánh giá, nên một số ngày tuyệt đối hợp lý vẫn có thể bị tính là unsupported.
Điều này có thể làm giảm faithfulness, nhưng không giải thích thay cho `answer_relevancy` rất thấp và
không đủ căn cứ để đổi trạng thái FAIL thành PASS.

### 3.6 Formal Agent acceptance mới

Runner dùng 17 case trong `user_agent_acceptance_v1.json`, PostgreSQL test cô lập và model
`openai/gpt-5.6-luna` qua OpenRouter. Kết quả được tạo lúc `2026-08-28T05:57:27Z` trên code mới.

| Metric | Kết quả | Gate | Trạng thái |
|---|---:|---:|---|
| Case pass rate | 29,4% (5/17) | >= 80% | **FAIL** |
| Tool routing accuracy | 60,0% | >= 95% | **FAIL** |
| Task precision | 66,7% | >= 90% | **FAIL** |
| Task recall | 100% | >= 90% | **PASS** |
| Task due accuracy | 100% | >= 90% | **PASS** |
| Memory isolation pass rate | 0% | 100% | **FAIL** |
| Forbidden claim rate | 0% | 0% | **PASS** |
| Side effect trước HITL | 0% | 0% | **PASS** |

Các case pass: `ROUTE-01`, `ROUTE-02`, `TASK-01`, `MEM-CANDIDATE-01`, `READ-01`. Mười hai case còn
lại fail, tập trung ở reminder/HITL routing, summary, multi-task extraction, memory retrieval/isolation
và `SEC-01`. Latency Agent P50 là 5,276 giây, P95 là 11,889 giây. `unsupported_claim_rate=75%` và
memory isolation 0% là rủi ro nghiêm trọng cần phân tích theo từng check trước release.

Artifact mới duy nhất là `eval/results/agent_acceptance_latest.json/.md`; hai artifact rerun lịch sử
đã bị xóa để tránh nhầm kết quả.

### 3.7 Task extraction mới

Runner dùng model `openai/gpt-5.6-luna`, ngày neo `2026-08-28`, timezone `Asia/Ho_Chi_Minh` và 13 case
hiện có trong code mới.

| Metric | Kết quả | Gate runner | Gate sản phẩm |
|---|---:|---:|---:|
| Title precision | 83,3% | PASS (>= 70%) | **FAIL** (>= 90%) |
| Title recall | 83,3% | PASS (>= 70%) | **PASS** (>= 80%) |
| Title F1 | 83,3% | PASS (>= 70%) | **FAIL** (>= 85%) |
| Date accuracy | 100% (8/8) | PASS (>= 70%) | **PASS** (>= 90%) |

Hai case miss là `single_task_relative_date` và `two_speakers_two_tasks`. Vì threshold trong runner
(70%) thấp hơn release gate chính thức trong `metric.md`, báo cáo release dùng gate sản phẩm và giữ
trạng thái FAIL cho precision/F1 dù script trả exit code 0.

### 3.8 Latency local

Mỗi endpoint được warm-up 10 request, sau đó đo 100 request với concurrency 10 trên backend local và
PostgreSQL test local.

| Endpoint | Success | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|
| `GET /health` | 100% | 13,250 ms | 21,238 ms | 23,765 ms | 24,403 ms |
| `GET /ready` | 100% | 963,389 ms | 1.185,869 ms | 1.344,410 ms | 1.412,458 ms |

`/ready` pass gate 5 giây nhưng chậm hơn `/health` khoảng hai bậc độ lớn vì kiểm tra DB/schema cho mỗi
request. Đây là baseline local, không thay thế đo staging/production có network latency và connection
pool thực tế. Chưa có kết quả `/api/v1/chat` vì app provider hiện chưa có credential tương ứng.

## 4. Khoảng trống và rủi ro ưu tiên

### P0 — chặn release

1. **RAGAS fail hai gate.** Cần phân tích failure theo case, cố định quy ước ngày tương đối/tuyệt đối,
   chạy lại trên dataset frozen và chỉ release khi cả bốn metric đạt.
2. **Formal Agent mới fail.** Chỉ 5/17 case pass; routing 60%, memory isolation 0% và unsupported claim
   rate 75% chưa đủ an toàn để release.
3. **Task extraction chưa đạt gate sản phẩm.** Precision và F1 cùng 83,3%, thấp hơn ngưỡng tương ứng
   90% và 85%, dù runner nội bộ với threshold 70% báo pass.
4. **Thiếu user validation và chat latency.** CSV feedback đang có 0 participant; chưa đo model thật
   trên endpoint chat.

### P1 — nên xử lý trước production pilot

1. **People intelligence gần như chưa có test trực tiếp.** Service mới có coverage 16,6%, được gọi từ
   planner và có thể đưa email, role, interaction metrics và private note của người dùng vào prompt.
   Cần test permission, workspace isolation, revoked membership, prompt injection trong private note,
   query ranking và giới hạn dữ liệu trước khi coi feature này là production-ready.
2. **Memory harness không thực sự chứng minh PostgreSQL như README mô tả.** `tests/conftest.py` đặt
   `DATABASE_URL=sqlite+aiosqlite:///:memory:` trước khi import application; `run_memory_harness.py`
   chỉ kiểm tra `TEST_DATABASE_URL` rồi gọi pytest, không map URL đó thành database runtime. Vì vậy
   memory/agent-quality harness hiện chứng minh logic repository trên SQLite. Chỉ test checkpoint riêng
   trong `test_postgres_checkpointer.py` thực sự dùng PostgreSQL.
3. **Coverage thấp ở các boundary quan trọng.** Chat, workspace, task, calendar và service mới còn
   nhiều nhánh error/authorization chưa có bằng chứng.
4. **Bundle Calendar lớn.** Cần đo tải trang thật và tách chunk nếu ảnh hưởng LCP/INP.
5. **Cấu hình model mặc định của deployment chưa sẵn sàng.** `.env` chọn Google nhưng chưa có
   `GOOGLE_API_KEY`. Formal evaluation chạy được qua cấu hình OpenAI-compatible/OpenRouter chỉ đặt ở
   process runtime; cấu hình production thực tế vẫn phải được xác nhận riêng.

## 5. Cách triển khai đánh giá có thể tái lập

### 5.1 Nguyên tắc an toàn

- Luôn dùng database disposable có tên kết thúc bằng `_test`, `_tests` hoặc `_harness`.
- Không đặt `TEST_DATABASE_URL` bằng `DATABASE_URL` của dev/staging/production.
- Không commit API key, database password, raw chat hoặc dữ liệu cá nhân vào artifact.
- Ghi commit SHA, tree SHA, model, dataset version, timestamp và timezone trong mỗi report.
- Kết quả thiếu phải là `PENDING`/`BLOCKED`, không tự chuyển thành PASS.
- Formal agent runner reset toàn bộ `public` schema; tuyệt đối không trỏ nó vào database dùng chung.

### 5.2 Chuẩn bị dependency

```powershell
cd D:\deploy\copy_build_phase
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,eval]"

cd Frontend\user
npm ci
cd ..\admin
npm ci
cd ..\..
```

### 5.3 Tạo PostgreSQL test

Cách khuyến nghị nếu Docker hoạt động:

```powershell
docker run --name orbit-eval-postgres `
  -e POSTGRES_USER=orbit_eval `
  -e POSTGRES_PASSWORD=<strong-test-password> `
  -e POSTGRES_DB=orbit_agent_eval_test `
  -p 127.0.0.1:55432:5432 `
  -d postgres:17

$EvalDbUrl = "postgresql+asyncpg://orbit_eval:<url-encoded-password>@127.0.0.1:55432/orbit_agent_eval_test"
```

Lần đánh giá trong báo cáo này dùng PostgreSQL 17 local cluster riêng vì Docker daemon không chạy:

```powershell
$PgBin = "C:\Program Files\PostgreSQL\17\bin"
$EvalData = "D:\deploy\.orbit-postgres-eval-20260828"

& "$PgBin\initdb.exe" -D $EvalData -U orbit_eval -A trust --encoding=UTF8 --locale=C
& "$PgBin\pg_ctl.exe" -D $EvalData -l "$EvalData\postgres.log" `
  -o '"-h 127.0.0.1 -p 55432"' -w start
& "$PgBin\createdb.exe" -h 127.0.0.1 -p 55432 -U orbit_eval `
  -T template0 -E UTF8 orbit_agent_eval_test

$EvalDbUrl = "postgresql+asyncpg://orbit_eval@127.0.0.1:55432/orbit_agent_eval_test"
```

`trust` chỉ chấp nhận được cho cluster test disposable bind tại localhost. Không dùng cấu hình này
cho server chia sẻ hoặc production.

Sau khi hoàn tất đánh giá, có thể dừng instance mà không xóa dữ liệu test:

```powershell
# Nếu dùng Docker
docker stop orbit-eval-postgres

# Nếu dùng local cluster của báo cáo này
& "$PgBin\pg_ctl.exe" -D $EvalData -w stop
```

Chỉ xóa container/data directory khi đã xác nhận không cần giữ artifact hoặc tái chạy đánh giá.

### 5.4 Kiểm tra migration PostgreSQL

```powershell
$env:DATABASE_URL = $EvalDbUrl
$env:APP_ENV = "test"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
Remove-Item Env:DATABASE_URL
Remove-Item Env:APP_ENV
```

Expected: revision hiện tại là `20260826_25`, không có exception.

### 5.5 Chạy full backend suite và coverage trên Windows

Không dùng Proactor event loop cho psycopg async. Dùng thư mục tạm mới cho mỗi lần chạy để tránh
`WinError 5` từ pytest `tmp_path` cũ.

```powershell
$ArtifactDir = "D:\deploy\orbit-eval-artifacts-$(Get-Date -Format yyyyMMdd-HHmmss)"
$BaseTemp = "D:\deploy\orbit-pytest-$(Get-Date -Format yyyyMMdd-HHmmss)"
New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
$env:TEST_DATABASE_URL = $EvalDbUrl

.\.venv\Scripts\python.exe -c @"
import asyncio
import pytest

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
raise SystemExit(pytest.main([
    "tests", "-q", "-p", "no:cacheprovider",
    "--basetemp=$($BaseTemp -replace '\\', '/')",
    "--cov=src", "--cov-branch", "--cov-fail-under=60",
    "--cov-report=term",
    "--cov-report=json:$($ArtifactDir -replace '\\', '/')/coverage.json",
    "--junitxml=$($ArtifactDir -replace '\\', '/')/test-results.junit.xml",
]))
"@

Remove-Item Env:TEST_DATABASE_URL
```

Expected: 410 test pass, không skip PostgreSQL checkpoint, coverage >= 60%.

Có thể chạy riêng checkpoint để chẩn đoán nhanh:

```powershell
$env:TEST_DATABASE_URL = $EvalDbUrl
.\.venv\Scripts\python.exe -c @"
import asyncio
import pytest
asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
raise SystemExit(pytest.main(["tests/test_agents/test_postgres_checkpointer.py", "-q"]))
"@
Remove-Item Env:TEST_DATABASE_URL
```

### 5.6 Static check, build và dependency audit

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\ruff.exe check src tests scripts

cd Frontend\user
npm run build
npm audit --omit=dev --audit-level=high

cd ..\admin
npm run build
npm audit --omit=dev --audit-level=high
cd ..\..
```

### 5.7 Chạy RAGAS

RAGAS dùng OpenRouter và tiêu tốn quota. Khóa model/dataset trước khi so sánh hai lần chạy.

```powershell
$env:OPENROUTER_API_KEY = "<secret>"
$env:RAGAS_APPLICATION_MODEL = "openai/gpt-5.6-luna"
$env:RAGAS_EVALUATOR_MODEL = "openai/gpt-5.6-luna"
$env:RAGAS_EMBEDDING_MODEL = "openai/text-embedding-3-small"

.\.venv\Scripts\python.exe scripts/eval_ragas.py `
  --output-json "$ArtifactDir\ragas.json" `
  --output-md "$ArtifactDir\ragas.md"

Remove-Item Env:OPENROUTER_API_KEY
```

Gate hiện tại: faithfulness và answer relevancy >= 0,70; context precision và recall >= 0,60.
Runner trả exit code 1 nếu bất kỳ gate nào fail; exit code 1 có report hợp lệ khác với lỗi runner/credential.

### 5.8 Chạy formal user-agent acceptance

Runner này dùng provider của ứng dụng, không dùng `OPENROUTER_API_KEY` của RAGAS. Ví dụ với Google:

```powershell
$env:LLM_PROVIDER = "google"
$env:MODEL_NAME = "gemini-2.5-flash"
$env:GOOGLE_API_KEY = "<secret>"
$env:AGENT_EVAL_DATABASE_URL = $EvalDbUrl

.\.venv\Scripts\python.exe scripts/eval_user_agent.py `
  --json-report "$ArtifactDir\agent-acceptance.json" `
  --markdown-report "$ArtifactDir\agent-acceptance.md"

Remove-Item Env:GOOGLE_API_KEY
Remove-Item Env:AGENT_EVAL_DATABASE_URL
```

Runner có 17 case, gọi model thật, tiêu tốn quota và reset schema test trước/sau run. Không đánh giá
release bằng artifact cũ nếu source revision hoặc model thay đổi.

### 5.9 Chạy task extraction

```powershell
$env:LLM_PROVIDER = "google"
$env:MODEL_NAME = "gemini-2.5-flash"
$env:GOOGLE_API_KEY = "<secret>"

.\.venv\Scripts\python.exe scripts/eval_extract_tasks.py `
  --as-of 2026-08-28 `
  --output "$ArtifactDir\task-extraction.json"

Remove-Item Env:GOOGLE_API_KEY
```

Ngày `--as-of` phải cố định trong report để chấm “hôm nay/ngày mai/thứ Hai tới” tái lập được.

### 5.10 Đo latency local/staging

Terminal A, chạy backend bằng launcher Windows có Selector event loop:

```powershell
$env:DATABASE_URL = $EvalDbUrl
$env:APP_ENV = "test"
.\.venv\Scripts\python.exe scripts/run_dev.py
```

Terminal B:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_api_latency.py `
  --base-url http://127.0.0.1:8000 --endpoint /health `
  --requests 100 --warmup 10 --concurrency 10 `
  --output-json "$ArtifactDir\latency-health.json" `
  --output-md "$ArtifactDir\latency-health.md"

.\.venv\Scripts\python.exe scripts/benchmark_api_latency.py `
  --base-url http://127.0.0.1:8000 --endpoint /ready `
  --requests 100 --warmup 10 --concurrency 10 `
  --output-json "$ArtifactDir\latency-ready.json" `
  --output-md "$ArtifactDir\latency-ready.md"
```

Với `/api/v1/chat`, cần bearer token test, provider key hợp lệ và phải ghi rõ model, dataset, warm/cold,
concurrency, timeout và tỷ lệ provider error. Kết quả local không thay thế benchmark staging.

### 5.11 User feedback

1. Thu thập tối thiểu 5 participant ẩn danh theo `eval/user_feedback/README.md`.
2. Không ghi email, số điện thoại hoặc raw chat vào CSV.
3. Chạy:

```powershell
.\.venv\Scripts\python.exe scripts/summarize_user_feedback.py `
  --input eval\user_feedback\responses.csv `
  --minimum-participants 5 `
  --output-json "$ArtifactDir\user-feedback.json" `
  --output-md "$ArtifactDir\user-feedback.md"
```

### 5.12 Tổng hợp và quyết định release

Chỉ chạy `scripts/generate_evaluation_evidence.py` khi chủ động muốn cập nhật file tracked
`eval/EVALUATION_EVIDENCE.md`; script không có chế độ `--help` và chạy trực tiếp sẽ ghi file đó.

Quy tắc quyết định:

1. Backend test/build/static/dependency gate phải pass.
2. Migration và PostgreSQL integration phải pass trên DB disposable.
3. Tất cả RAGAS gate và formal acceptance gate phải pass trên artifact mới gắn commit SHA.
4. Privacy, authorization, HITL hoặc duplicate-side-effect fail thì dừng release ngay.
5. Feedback dưới 5 participant, chat latency chưa đo hoặc artifact cũ đều giữ trạng thái `PENDING`.
6. Chỉ chuyển sang `PASS/RELEASE` khi không còn `FAIL`, `PENDING` hoặc bằng chứng không gắn revision ở
   các mục P0.

## 6. Việc cần làm để chuyển từ HOLD sang RELEASE

1. Chuẩn hóa RAGAS date anchor giữa prompt, context và reference; phân tích từng case fail rồi chạy lại
   trên dataset/model frozen.
2. Phân tích 12 case formal Agent fail, ưu tiên memory isolation, unsupported claim và tool routing;
   sau đó chạy lại đủ 17 case trên cùng model/dataset.
3. Sửa hai nhóm lỗi task extraction (relative-date title matching và multi-speaker attribution), rồi
   chạy lại 13 case với ngày `as-of` cố định đến khi đạt gate sản phẩm.
4. Bổ sung bằng chứng test cho people intelligence, đặc biệt isolation/private-note injection.
5. Sửa quy trình memory harness để PostgreSQL URL thực sự được dùng, sau đó chạy lại trên PostgreSQL.
6. Đo `/api/v1/chat` trên staging và thu thập ít nhất 5 participant feedback.
7. Chạy lại toàn bộ regression cuối cùng và gắn artifact với commit SHA chuẩn bị phát hành.
