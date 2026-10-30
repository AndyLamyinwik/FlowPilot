# Phase 07A — Full Project Audit & Bug Fixing

審查日期：2026-10-29（Asia/Shanghai）

後續狀態：本文件保留 Phase 07A 當時的發現與測試。Phase 07B 已強化 FP07A-005 的前後端 Host 邊界。Phase 09 經使用者明確批准後修復 FP07A-002 列表隔離，保留嚴格編輯精度檢查並通過回歸與實際瀏覽器／API 驗證；FP07A-003／004 仍保留。最新部署與發布驗收見 [PHASE_09_RELEASE_REPORT.md](PHASE_09_RELEASE_REPORT.md)，以下發現與測試保留當時記錄。

## Overview

**Overall Status：PASSED WITH WARNINGS。** 已完成現有核心模組審查、基準測試、最小必要修復與完整回歸。確認 1 個 P1 並修復；另有 3 個已重現的 P2 功能問題及 1 個 P2 安全強化缺口，保留於下文。審查範圍內未確認其他 P0／P1，不代表已完成全面安全認證或生產部署驗收。

本次只修復 1 個獨立問題，沒有用滿最多 5 個修復名額，沒有新增產品功能、重寫引擎、改變資料庫 Schema、升級依賴或建立大型 E2E 框架。

### Repository and Environment

- 已閱讀 AGENTS、README、ARCHITECTURE、PROJECT_STATUS、依賴來源及鎖定檔、Docker／Compose 和現有測試配置。目錄沒有 `.git`；`git status --short` 回報不是 Git Repository，無法藉 Git 判定未提交修改。保留現有檔案，沒有初始化／reset／clean／commit／push。
- 沒有既有 `.github`／CI Configuration，沒有可報告的 CI 執行結果；本次沒有另建 CI。
- 使用現有 Python 3.12.14、Node 24.22.1、專案本地 npm CLI 11.21.1、uv 0.13.6、standalone Compose 5.6.0。直接依賴固定版本、`uv.lock`、附雜湊 requirements 及 `package-lock.json` 均保留，沒有重新解析或升級依賴。
- Docker Engine／Desktop 不可用，只能驗證 Compose 配置，不能聲稱映像建置／容器執行通過。
- 所有執行／資料測試使用 pytest 暫存目錄、TemporaryDirectory 或被忽略的 `.tools/phase07a-*`。正式 `data/flowpilot.db` 仍為 0 bytes，前後 SHA-256 均為 `E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855`。

### Coverage

| 範圍 | 審查及驗證 |
| --- | --- |
| API／Models／Registry／Validation | 路由、OpenAPI、Pydantic 與資料庫模型分離、Draft 保存、版本／JSON／密鑰欄位限制、UUID／404／409／422／503；Registry 只管理 Metadata |
| Engine／Condition | 確定性拓撲、所有上游狀態確定、分支啟動、Join、skipped、fail-fast、Context 隔離、直接 input 與成功路徑 ancestor_outputs |
| 七種 Executors | Manual／Schedule／Logger／HTTP／Condition／Transform／Webhook，合法來源、路徑、無副作用 readiness、共用 HTTP 安全政策 |
| Scheduler／Lifespan | 單實例啟動、OS instance lock、固定 Job ID、停用／刪除／更新、恢復、Misfire、互斥 finally 釋放、同一 Execution Service |
| SQLite／History | 追加式初始化、參數化 SQL、短交易、FK／索引、Execution ID、隱私、大小限制、interrupted 恢復與保留清理 |
| Frontend | Dashboard、Editor、Library／Properties、Adapter、API Client、Run／Validation、Node ID 狀態、History／Detail、Schedule 確認與版本／取消隔離 |
| Deployment／Security | 預設 loopback、單 Worker／Replica、CORS、HTTP Allowlist／DNS／IP／SNI／redirect、輸出遮罩、任意程式碼／HTML 注入風險搜尋 |

## Baseline Tests

先執行低成本配置、既有單元／元件測試及構建，再進行本機 smoke；沒有先建立大型瀏覽器測試環境。

| 工作目錄 | 實際指令 | 結果 |
| --- | --- | --- |
| backend | `.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest_cache/phase07a-baseline-retry -q --tb=short` | **589 passed in 8.66s** |
| frontend | `node .tools/npm11/package/bin/npm-cli.js test` | **274 passed，19 files，7.99s** |
| frontend | `node .tools/npm11/package/bin/npm-cli.js run typecheck` | 通過 |
| frontend | `node .tools/npm11/package/bin/npm-cli.js run build` | 通過，197 modules，無警告 |
| 根目錄 | `.\.tools\compose\docker-compose.exe config --quiet` | 通過，exit 0 |
| 根目錄 | `.\.tools\compose\docker-compose.exe --env-file .env.example config --quiet` | 通過，exit 0 |
| 根目錄 | `.\.tools\bin\uv.exe lock --check --offline --project backend --cache-dir .tools/uv-cache --python backend/.venv/Scripts/python.exe` | 通過，30 packages |

初次受限沙箱中的 pytest／Vitest 未完成，已中止，未視為通過；uv 使用預設沙箱快取時出現拒絕存取。上述測試使用可用的執行權限重跑，uv 改用專案內快取。pytest 的啟動測試已確認 FastAPI、SQLite 表格初始化、CORS 及資料保留；後續真實 Uvicorn smoke 另行確認。

## Issues Found

| ID | Severity | Module | Description | Status |
| --- | --- | --- | --- | --- |
| FP07A-001 | P1 | Backend History／API identity | 長 Node ID 被截成相同前綴，造成歷史節點身份碰撞，前端拒絕 Detail | **Fixed** |
| FP07A-002 | P2 | Frontend list／Dashboard／Open | 一個超出瀏覽器安全整數範圍的配置令整個列表驗證失敗 | Open，已重現 |
| FP07A-003 | P2 | ExecutionPanel selection | 刪除節點後，保留結果的本地選取被目前畫布選取覆蓋 | Open，已重現 |
| FP07A-004 | P2 | History pagination API | offset 超出 SQLite int64 時回傳 500，應為 422 | Open，已重現 |
| FP07A-005 | P2 | Backend Host boundary | 接受任意 Host；缺少 Host 驗證，可能涉及 DNS rebinding | Open，安全強化缺口；完整瀏覽器利用未驗證 |

P2 以記錄為主，沒有為增加修復數量而修改不相關模組。

## Issues Fixed

### FP07A-001 — Preserve History Node Identity

- **Description／Affected Module**：合法的不同 Node ID 在保存歷史時變成同一 ID，破壞執行結果、錯誤與歷史之間的身份契約。
- **Reproduction Steps**：建立 Manual → Logger，兩個 ID 長於 256 字元且前 256 字元相同；保存並 Execute，再 GET `/api/executions/{execution_id}`。隔離重現中 Live 的兩個 266 字元 ID 唯一，原歷史只剩一個唯一前綴。
- **Expected Behavior**：保留完整且相異的 Node ID；大小限制以省略完整摘要表達，不改造身份值。
- **Actual Behavior before Fix**：`HistoryService._label()` 截取前 256 字元；`error.node_id` 亦被截短。前端 `executionApi.nodes()` 拒絕重複 ID，Detail 無法載入。
- **Root Cause**：將 ID 當作可裁切顯示標籤，與沒有此長度限制的公開 Schema 不一致。
- **Files Changed**：`backend/app/services/history.py`、`backend/tests/test_history_service.py`。
- **Fix Description**：移除 ID 截斷，保留節點及錯誤的完整參照。沿用整筆記錄預算：先捨棄輸出，再省略完整節點摘要；若頂層錯誤的 ID 本身已使空節點記錄超限，省略該 nullable 參照為 null，標示 `history_truncated=true`。不修改即時結果、不改 Schema 或預設預算。
- **Verification**：新增兩項回歸，先 RED **2 failed**，修復後相關 History／Execution Service **36 passed**，擴大 Scheduler／History／Service **62 passed**。真實 REST smoke 另外確認長 ID 的 Live／Detail 完全一致且未假報截減。
- **Limit**：修復適用於此後寫入。過去已截短的歷史無法可靠還原，沒有猜測或改寫既有資料；既有受影響 Detail 仍可能被前端拒絕。

實際 RED／GREEN 指令（backend）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_history_service.py -k 'preserves_distinct_long_node_ids or omits_oversized_error_reference' --basetemp=.pytest_cache/phase07a-history-red -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_history_service.py tests/test_execution_service.py --basetemp=.pytest_cache/phase07a-history-green -q --tb=short
.\.venv\Scripts\python.exe -m pytest tests/test_scheduler_service.py tests/test_history_service.py tests/test_execution_service.py --basetemp=.pytest_cache/phase07a-scheduler-history -q --tb=short
```

## Remaining Issues

### FP07A-002 — One Uneditable Workflow Blocks the List

- **Reproduction**：列表包含一個普通工作流，另一個 Transform 的靜態值為 `9007199254740992`。這是合法後端 JSON，但超出前端編輯安全範圍。
- **Expected／Actual**：應可列出及開啟其他正常工作流；目前 `listWorkflows()` 對每項 Definition 套用編輯精度檢查，整份列表被拒絕，Dashboard／Open 顯示載入錯誤。
- **Root Cause／Suggested Fix**：讀取摘要與編輯 Definition 共用同一嚴格 guard。後續分開只讀列表驗證與安全編輯檢查，不可直接移除精度保護或保存已失真的數字。
- **Workaround**：以 `/editor?id=<正常工作流 UUID>` 直接開啟；大型識別碼配置使用字串。一般由目前 Editor 保存的配置不會產生此情況。

### FP07A-003 — Stale Result Node Selection

- **Reproduction**：執行 A／B → 刪除 B → 在畫布選取 A → 在保留的舊 Execution Result 按 B。
- **Expected／Actual**：應可查看 B 的舊執行詳情；目前詳情持續顯示 A。原始結果沒有遺失，獨立 Historical Detail 不受影響。
- **Root Cause／Suggested Fix**：`ExecutionPanel` 優先採 `selectedNodeId ?? localNodeId`，Editor 對不存在於目前畫布的節點不改選取。後續分開結果選取與畫布定位，尤其 stale execution，不把舊結果套用目前圖形。
- **Workaround**：清除目前畫布選取後查看，或到 History 的獨立 Detail。

### FP07A-004 — Oversized History Offset

- **Reproduction**：建立工作流後請求 `/api/workflows/{id}/executions?offset=9223372036854775808`。
- **Expected／Actual**：應回傳 422；實際為安全的 `500 {"detail":"Internal server error"}`，後續 health 仍正常。
- **Root Cause／Suggested Fix**：Query 只有 `ge=0`，任意 Python int 直接綁定 SQLite int64 OFFSET。後續增加明確上限及邊界測試。
- **Workaround**：使用目前 UI 分頁或有效 int64 offset；不要傳送不受支援的極端值。

### FP07A-005 — Host Validation Hardening

- **Reproduction**：隔離 TestClient 對既有 API 帶 `Host: rebind.example.invalid:8000` 與相同 Origin。Create 回 201、Update 回 200、Manual Execute 回 200／success。
- **Expected／Actual**：若部署要抵禦未知 Host 的存取，應拒絕非允許名稱；目前只有 CORS，沒有 Host 檢查。CORS 也不是身分驗證或阻止副作用的授權機制。
- **Boundary**：只證實伺服器接受任意 Host，**沒有驗證完整 DNS rebinding 瀏覽器攻擊**，未將其描述為已證實的遠端利用漏洞。
- **Mitigation／Suggested Fix**：維持 loopback／可信環境；若有可信反向代理，由其拒絕未知 Host。後續明確設計允許名稱政策並驗證 localhost、IP、Compose backend 代理及自訂主機名，不在本次擅自建立認證系統。

002／003 使用被忽略的隔離 Vitest reproduction 確認，當次指令為 `node .tools/npm11/package/bin/npm-cli.js test -- .tools/phase07a-audit/frontend-findings.test.tsx`，**2 passed in 1.18s**。這兩項斷言刻意證實缺陷，**不是修復通過**；檔案後改名 `frontend/.tools/phase07a-audit/frontend-findings.repro.tsx`，不加入正式回歸計數。004／005 由 `.tools/phase07a-contract-audit.py` 驗證，exit 0；無效 Unicode 名稱另外確認為 422。

## Security Findings

- 正常執行路徑未發現 config 使用 Python `eval`／`exec`、Shell、任意模組載入或任意本地檔案讀取；前端沒有不安全 HTML 注入入口，輸出以文字／JSON 呈現。搜尋中的 JavaScript RegExp `.exec()` 是正規表示式方法。
- HTTP／Webhook 共用同一安全 Client：預設空精確 allowlist、HTTPS、公網位址檢查、全部 DNS 回應檢查、數字 IP 固定、原始 Host／TLS SNI、TLS 驗證、禁止 redirect／環境 proxy／憑證 Header、有限 timeout／大小及沒有自動重送。現有底層 MockBackend 測試驗證 TCP IP 與 SNI；本次沒有真實外部請求。
- 同步 OS DNS／已開始的 I/O 不能即時硬中斷；這些應用層限制不能替代部署端 DNS、路由、TLS 信任及 egress 控制。沒有完成真實外網／Linux 容器 TLS 驗證，不宣稱完整 SSRF 防護。
- SQLite 參數化 SQL、追加式初始化、短交易與 FK 存在；保留測試涵蓋 hostile SQL 文字、不破壞既有資料及重啟恢復。
- 一般 Schema／Executor／儲存錯誤回應使用受控訊息，沒有發現正常 Executor 將 config、環境或 Payload 寫入日誌；未預期的服務例外仍會記錄伺服器 traceback，部署者須保護日誌，不應把它視為保證不含任何內部資訊。
- 歷史預設不存輸出、input 或完整 config；opt-in 及前端都有有界顯示／常見敏感 key 遮罩，但不能辨識任意文字中的所有秘密，不能輸入真實密鑰作為工作流資料。
- Compose 主機埠仍只發布至 `127.0.0.1`、workers=1／replicas=1；V1 沒有認證，Host 缺口見 FP07A-005。不可將目前設定描述為可公開部署的安全方案。

## Regression Results

| 實際指令／檢查 | 結果 |
| --- | --- |
| backend：`.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest_cache/phase07a-final -q --tb=short` | **591 passed in 8.94s**，原 589 項保留，新增 2 項 |
| frontend：`node .tools/npm11/package/bin/npm-cli.js test` | **274 passed，19 files，4.53s** |
| frontend：`node .tools/npm11/package/bin/npm-cli.js run typecheck` | 通過 |
| frontend：`node .tools/npm11/package/bin/npm-cli.js run build` | 通過，197 modules；JS 486.10 kB／gzip 150.25 kB，無警告 |
| Engine／HTTP／Data 專項既有測試 | **247 passed in 0.76s**，指令見下 |
| 根目錄：`.\backend\.venv\Scripts\python.exe .tools/phase07a-engine-audit.py` | 400 個固定種子、2–30 節點 DAG 通過獨立路徑啟動參考檢查 |
| 根目錄：`.\backend\.venv\Scripts\python.exe .tools/phase07a-contract-audit.py` | exit 0，確認 004／005 邊界與安全錯誤，非缺陷修復 |
| 根目錄：`.\backend\.venv\Scripts\python.exe .tools/phase07a_http_smoke.py` | exit 0，以下最小實際整合通過 |
| Compose default／example、uv lock | 基準已通過，配置／依賴未修改 |
| Docker build／容器啟動、完整瀏覽器 E2E、CI | **未執行**；Docker／CI 不可用，完整 E2E 留待 07B |

Engine 專項指令（backend）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_http_security.py tests/test_http_nodes.py tests/test_data_nodes.py tests/test_data_reference.py tests/test_phase04_branches.py tests/test_execution_engine.py tests/test_execution_validation.py -q --tb=short --basetemp=.pytest_cache/phase07a-engine-http-audit
```

400 個 DAG 檢查不是新的產品測試平台；它對照獨立的啟動路徑參考，核對直接 input、成功祖先、selected／skipped、每節點最多一次及隨機 Definition 順序。原套件另涵蓋循環拒絕、fail-fast、兩種 Condition 分支與全跳過 Join。

### Real Local Smoke

使用真實 Uvicorn、Vite、APScheduler、現有 API／Engine 與獨立 SQLite，全部只綁定 `127.0.0.1`，無外部服務：

1. health、Create／List／Read／Update、POST Validate、OpenAPI 全部既有路由。
2. Manual → Logger 成功、Execution ID／History 一致、歷史 output=null。
3. FP07A-001 長 ID 經真實建立／執行／歷史 API 完整保留。
4. 將已註冊測試 Cron Job 的到期時間受控推進，真實 APScheduler 派發並記錄 schedule success；沒有增加 Run Now API。
5. 真實 Vite 首頁與 `/api/health` 代理。
6. 服務重啟後工作流／歷史／enabled Job 恢復，停用清除 Next Run，刪除移除 Job。
7. 關閉所有臨時服務，正式資料庫 hash 不變。

Smoke 首次使用舊腳本的 3 秒首頁等待，Vite 冷啟動讀取超時；擴充腳本時也曾誤用 GET Validate 得到 405。兩次均未列為通過，已修正測試腳本等待為 30 秒與方法為既有 POST，最終完整成功。沒有為此改產品或降低斷言。最終證據位於被忽略的 `.tools/phase07a-http/4aa7e5df-a3b0-48b0-8766-5cfd70475935/evidence.json`。

## Phase 07B Recommendations

1. 先排程處理 FP07A-002～005：列表隔離、舊結果選取、OFFSET 邊界與經驗證的 Host 政策；不可為解決列表問題移除數字精度保護。
2. 在具備 Docker Engine 的環境實際 build／up，驗證 Linux OS lock、volume／權限、冷啟動、health、API proxy、停止重建及資料保留。
3. 執行完整瀏覽器 Create → Configure／Condition Handles → Save → Reload → Run → Result／History，涵蓋 failed／skipped、取消等待、未保存變更與排程啟停／重啟。
4. 在受控網路驗證真實 TLS／SNI、IPv6／DNS／redirect 限制，補上 Host 威脅模型；不使用付費服務或真實密鑰。
5. 檢查長執行／Misfire／並行變更與關閉；完成歷史寫入失敗可能留 running 至下次啟動，重啟不得重放副作用。歷史總數／頁面也非並行寫入的一致快照。
6. 本地回歸已可執行，後續另行決定 CI。只有一個 Scheduler／Worker owner，不引入分散式、AI、認證或其他未授權產品能力。

**Phase 07A 到此完成；Phase 07B／08 未開始。**
