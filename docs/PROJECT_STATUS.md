# FlowPilot 專案狀態

更新日期：2026-10-30（Asia/Shanghai）

## 當前階段

**Phase 09：Final Acceptance & GitHub Publication — RELEASE_PARTIALLY_COMPLETED。** 已重新完成本地核心回歸與安全／版本／CI 配置核對。使用者後續明確要求立即上傳完整程式碼，因此把已審查的程式碼、測試、範例、Docker／CI 配置與文件 commit／push 至 [AndyLamyinwik/FlowPilot](https://github.com/AndyLamyinwik/FlowPilot) 的 main。原始碼公開與正式 tag／Release 分開驗收；原始碼不再以本機沒有 Docker 為由停留於空倉庫。

**正式版本發布判定仍 NOT_READY。** 本機沒有 Docker Engine；容器驗收與推送 Commit 的遠端 CI 結果須另行取得，不把原始碼上傳當作它們通過。完整來源可從 main 取得，沒有建立 v0.1.0 tag／GitHub Release 或發布 Image。Public 倉庫與已授權 ChatGPTBot 連接、私人漏洞回報設定均已確認；沒有提交測試漏洞或宣稱通知投遞已測。沒有改動產品程式碼、依賴或使用者資料。確切 Commit SHA／推送／CI 結果記錄於執行摘要及 [Commit History](https://github.com/AndyLamyinwik/FlowPilot/commits/main)，詳見 [PHASE_09_RELEASE_REPORT.md](PHASE_09_RELEASE_REPORT.md)。

原始碼已正常推送：`8847cf3605cc2a3dbcf3d6c892b6b5960609d232`，194 檔；[首輪遠端 CI](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/40920568507) 的後端、前端與 Docker 構建全部通過。後續 `679d2f4` 在同一 CI 加入隔離容器驗收；真實啟動／health／工作流執行／歷史／排程啟用通過，但 stop/start 步驟因 runner 的 Compose 不支援 start --wait 失敗。已移除該參數，保留完整健康與持久化斷言，待新 Commit 的遠端結果；不把失敗嘗試算作通過。

另已依使用者要求加入 [繁體中文介紹](../README.zh-TW.md)及[简体中文介绍](../README.zh-CN.md)，英文首頁提供語言切換，GitHub About 也包含英／繁／簡三種介紹。公開 Clone `679d2f4` 已核對完整 195 檔，隔離 npm ci --offline／typecheck／build 通過且 lockfile／Clone working tree 未變更。

### Phase 09 實際驗證（2026-10-30）

| 檢查 | 結果 |
| --- | --- |
| 完整後端 Pytest | **PASS：796 passed in 10.50s**，包含 API／Engine／Executors／Scheduler／History／AI Mock／範例 |
| 前端 Vitest | **PASS：274 passed，19 files，23.94s** |
| 正式前端服務測試 | **PASS：12 passed，0 skipped**；第一次受 sandbox loopback EACCES 阻擋，保留紀錄後以核准權限重跑通過，沒有改程式碼或降低安全限制 |
| TypeScript／production build | **PASS**，197 modules |
| Compose default／.env.example、actionlint | **PASS**，僅配置與語法，不代表 Docker／遠端 CI |
| 安全與版本核對 | **PASS（有限範圍）**，最終 183 文字檔掃描無未解決疑似真實憑證；測試假資料已核對，117 保護檔案雜湊與 107 runtime 路徑不變，應用版本均 0.1.0，AI 只有 Mock |
| 文件驗證 | **PASS**，16 份 Markdown／134 個相對連結，無 UTF-8 錯誤／壞連結／未關閉 fence |
| GitHub 帳號／目標倉庫 | **PASS**，使用者提供的帳號與已建立的 Public 倉庫吻合；metadata 回傳 admin／push=true；特定 collaborator-permission endpoint 因 integration scope 回傳 403，不冒充寫入測試通過 |
| 初始遠端 refs／版本衝突 | **PASS（上傳前）**，git ls-remote 成功且沒有 branch／tag refs；不覆蓋既有歷史或版本 |
| 本地 Git／候選檔案 | **PASS**，194 檔依明確清單審查與暫存，blob 與已審查檔案逐一相同，24 項 ignore 檢查通過，8 張截圖已檢視；依使用者最新授權 commit／push 原始碼 |
| Git 初次匯入空白格式檢查 | **FAIL（格式）**，diff --cached --check exit 2，16 檔共 482 項，主要既有 CRLF 與 EOF 空白；未為格式改寫原 LICENSE／程式碼／依賴，非產品測試失敗 |
| Docker build／startup／容器重建／持久化 | **NOT_TESTED — DOCKER_NOT_TESTED**，沒有 Docker CLI／Engine |
| GitHub Actions remote／版本發布驗證 | 推送後依確切 Commit 查詢，不以舊 Commit 或本地 PASS 代替；正式 Release 尚未建立 |
| 私人漏洞回報設定／入口 | **PASS**，依使用者另行授權啟用；公開頁面可見回報入口。實際提交／通知投遞 **NOT_TESTED** |

本次上傳完整已審查來源並更新發布文件與授權規範。正式資料庫仍為 0 bytes，測試使用隔離資料；不把先前本機 smoke 當作容器測試。下一步核對遠端來源／CI，並在 Docker 可用環境完成隔離容器驗收；不得直接將 Checklist 改為 READY 或開始 V0.2.0。

## Phase 08B 驗收記錄（2026-10-29）

**Phase 08B：GitHub Open Source Release Preparation 已完成本環境可執行的準備，等待維護者審核。** 候選版本為 **v0.1.0，未發布的 Early Public Release**。保留 Phase 01–08A；本階段只更新文件、三份範例及其測試、真實截圖和後端 Docker context 排除規則，沒有新增產品功能或真實 AI Provider。

**整體發布判定：NOT_READY。** Docker runtime／持久化驗收、遠端 GitHub Actions、實際 Git 追蹤／歷史及 Repository URL 檢查、私人漏洞回報管道仍有缺口。三個既有 P2 保留，未確認新的範圍內 P0／P1。準備文件與本地回歸通過不等於容器／遠端發布驗收通過，詳見 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)、[PHASE_07B_RELEASE_READINESS.md](PHASE_07B_RELEASE_READINESS.md) 及 [PHASE_07A_AUDIT.md](PHASE_07A_AUDIT.md)。

## Phase 08B 完成內容

- README 改為英文，涵蓋已實作功能、限制、實際 5173／8000 存取地址、Docker／本地開發入口、Explicit Save、第一個工作流、排程、安全配置、備份及文件索引。沒有虛構 Repository URL、發布日期、成功徽章或正式網站。
- 新增英文 [CONTRIBUTING.md](../CONTRIBUTING.md)、[SECURITY.md](../SECURITY.md)、[CHANGELOG.md](../CHANGELOG.md) 及 [v0.1.0 Release Notes](releases/v0.1.0.md)。Unreleased 與未發布 0.1.0 candidate 分開；安全回報管道待配置列為發布阻塞，沒有編造郵箱或聲稱 GitHub 私人回報已啟用。
- 新增 [Release Checklist](RELEASE_CHECKLIST.md)，使用 PASS／FAIL／NOT_TESTED／NOT_APPLICABLE／BLOCKED，記錄實際證據、版本策略、直接依賴授權聲明及 GitHub Description／Topics／About 建議；沒有修改遠端設定。
- 新增 [Workflow Examples](../examples/workflows/README.md)：Manual → Logger → Logger、UTC 每五分鐘 Schedule → Logger，以及 HTTP → Condition → true／false Logger。皆為目前 API 的 WorkflowCreate JSON；排程導入預設停用，HTTP 範例標示 Setup Required 並維持空 Allowlist 預設拒絕。
- 新增 `backend/tests/test_release_examples.py` 八項測試，驗證三份真實檔案解析／保存／結構、離線手動執行與歷史、排程停用、HTTP readiness 拒絕及受控 Mock Transport／DNS 的兩條分支，不呼叫真實外部服務。
- 在隔離 SQLite 與真實 Uvicorn／production dist + Node 服務中導入三份範例，只執行離線 Manual，取得成功歷史。以實際瀏覽器擷取 Dashboard／Editor／History 三張 1280×720 JPEG，已檢視並加入 README；不含私人資料、密鑰或本地檔案路徑。測試服務已停止、頁籤已關閉。
- 保留原 MIT LICENSE 與 `Copyright (c) 2026 FlowPilot contributors`，沒有改寫授權。檢查 23 個直接 runtime／development 套件的本地授權聲明（MIT、BSD-3-Clause、Apache-2.0），未發現明顯衝突；不是法律意見或完整遞迴依賴審計。
- 保留既有 `.gitignore` 與前端 `.dockerignore`；後端 `.dockerignore` 補上 DB journal／instance lock、本地工具和常見密鑰／credentials 檔案。沒有刪除 `.tools`、虛擬環境、node_modules、dist、快取或使用者資料。
- 有限的候選原始碼模式掃描未找到高可信密鑰模式或非預期敏感原始檔路徑；不輸出秘密值，不宣稱能辨識所有秘密。目錄沒有 `.git`，不能檢查 staged／tracked／歷史或確認遠端；維護者必須對實際發行來源重做檢查，不能把整個含本地產物的目錄直接打包。
- 既有應用程式碼、依賴與 lockfile、Compose／單一 CI、原 LICENSE、正式 `data/flowpilot.db` 的前後雜湊核對保持一致；資料庫仍為 0 bytes。沒有依賴升級、Git 初始化／commit／push／tag、GitHub Release 或 Docker Image 發布。

### Phase 08B 實際驗證

| 檢查 | 結果 |
| --- | --- |
| 發布範例專項 | **8 passed in 14.33s** |
| 完整後端 Pytest | **796 passed in 53.42s**，既有 788＋新增 8；包含 API／Engine／Scheduler／History／AI Mock |
| 前端 Vitest | **274 passed，19 files，53.01s** |
| Node production server tests | **12 passed，0 skipped** |
| TypeScript／production build | **PASS**，197 modules，沒有阻塞錯誤 |
| 真實本機 production 前後端與範例 | **PASS**，Health／匯入／Validate／Manual Execute／History，排程仍停用 |
| 真實截圖 | **PASS**，Dashboard／Editor／Execution History，非合成圖片 |
| Compose default／.env.example | **PASS**，standalone Compose 5.6.0；不能取代容器驗收 |
| 單一 CI／actionlint | **PASS**，保留 contents:read 及已核實完整 Action SHA；ShellCheck／Pyflakes 未執行 |
| 文件相對連結／fences／版本／圖片／保護檔案雜湊 | **PASS**，13 份 Markdown、80 個相對連結、182 份候選文字檔及 117 份保護檔案雜湊；沒有壞連結／未關閉 fence／UTF-8 錯誤或保護檔變更，版本一致為 0.1.0；Workflow Schema 仍為 1 |
| Docker build／startup／容器重建／Linux volume | **NOT_TESTED — DOCKER_NOT_TESTED**，沒有 Docker CLI／Engine；未聲稱部署成功 |
| 遠端 GitHub Actions | **NOT_TESTED**，沒有實際 workflow run |
| Git 追蹤／歷史敏感檔及正式 URL | **BLOCKED**，目錄沒有 `.git`／已確認遠端 |
| 私人漏洞回報管道 | **BLOCKED**，需要維護者配置並核實 |

實際命令、範例與截圖驗證範圍見 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。本階段沒有重新安裝依賴，沿用現有 lockfile；Phase 07B 的乾淨安裝與真實進程重啟證據只作先前驗證記錄，不冒充本次 Docker 測試。

### Phase 08B 剩餘問題與下一步

1. **R1**：在具備 Docker Engine 的環境建立隔離實例，完成 build／startup／前後端連通／容器重建／SQLite 權限與持久化／Scheduler 恢復。
2. **R2**：維護者確認實際 Repository URL 及發布來源，檢查 staged／tracked／Git 歷史、忽略檔案與第三方 notices；本地掃描不能證明 Git 歷史乾淨。
3. **R3**：配置並驗證私人漏洞回報管道，再更新 SECURITY 的待配置說明。
4. **R4**：在確認的 GitHub Repository 執行既有單一 CI，逐項查看遠端結果。
5. 三個既有 P2 保留：FP07A-002 大整數配置可阻擋列表、003 已刪節點的舊執行選取、004 超出 SQLite int64 的歷史 offset 回傳受控 500。詳見原審查；本階段不以無關重構擴大範圍。

暫不建議發布 v0.1.0。等待維護者處理以上阻塞、評估 P2 並覆核候選來源後再決定；Phase 08B 到此停止，不自動開始下一階段或發布。

## Phase 08A 完成內容

- 新增 `backend/app/ai/`，不依賴 FastAPI Request、Workflow Schema／DB、Execution Context、Scheduler 或前端。應用正常啟動不匯入 AI 模組。
- 唯一同步 `AIProvider` Protocol，包含 provider_id／provider_name／capabilities／generate；沒有同步與非同步雙重系統、Factory 或插件載入。
- Pydantic AIMessage／AIRequest／AIResponse／AIUsage／Provider Metadata：嚴格型別、非空模型／訊息、合法角色、可選有限 temperature／正整數 max_output_tokens；usage nullable／partial，不推算 Token。
- `AIProviderRegistry` 每個實例起初為空，顯式 register／get／list_providers；防止重複 ID，未知 Provider 有固定錯誤，清單只回獨立 Metadata 快照，不公開 Adapter 內部資料。
- 唯一 `MockAIProvider` 固定回應明示模擬文字，usage=null、metadata.mock=true，回應獨立、不讀 Key／環境、不回傳或記錄 Prompt、不發出 HTTP。錯誤僅由開發者建構參數 simulate_error=True 模擬。
- `AIProviderConfig` 包含 provider_id／default_model／enabled=false／timeout／base_url；沒有 Credential 欄位，URL 只作語法檢查、不是出站授權。統一 Provider 錯誤提供固定 code／訊息。
- Settings、.env.example、Compose 加入 FLOWPILOT_AI_ENABLED=false；true 仍不自動註冊或呼叫模型。V1 在沒有 AI 模組／Key 時仍正常。
- 新增 [AI_PROVIDER_GUIDE.md](AI_PROVIDER_GUIDE.md)，同步更新 README／ARCHITECTURE／AGENTS。沒有增加依賴或修改 lockfile，沒有修改 Engine、七種 Metadata／Executors、Condition、Scheduler、API、Workflow Schema／DB 或 UI。

### Phase 08A 實際驗證

| 檢查 | 結果 |
| --- | --- |
| Schema／Config 專項 | **124 passed in 0.37s** |
| Protocol／Registry／Mock 專項 | **40 passed in 0.85s** |
| AI 模組＋App 相容性完整專項 | **167 passed in 6.16s** |
| 完整後端回歸 | **788 passed in 48.12s**，包含既有 621 與新增 167 |
| 原有前端 Vitest | **274 passed，19 files，74.04s** |
| 原有 Node production server tests | **12 passed，0 skipped** |
| TypeScript／frontend build | **通過**，197 modules；build 有 plugin timing 提示，非構建錯誤 |
| Guide 同一 Python 範例 | **通過**，封鎖外部 DNS／連線、無 Key，固定 Mock JSON＋錯誤模擬 |
| 獨立 AI 程式審查及回歸 | **164 passed in 1.23s**；無剩餘範圍內阻塞問題 |
| Compose default／.env.example、uv lock offline | **通過**，AI 預設 false、原有安全配置保留 |
| Docker build／容器執行、遠端 GitHub Actions | **未執行**，沿用 Phase 07B 環境限制，不宣稱通過 |

實際命令（backend）：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ai_schemas.py tests/test_ai_config.py tests/test_ai_registry.py tests/test_ai_mock.py tests/test_ai_app_compatibility.py -q --tb=short --basetemp=.pytest_cache/phase08a-ai-final
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest_cache/phase08a-regression -q --tb=short
```

前端使用本地 npm CLI 實際執行 `node .tools/npm11/package/bin/npm-cli.js test`、`run test:server`、`run typecheck`、`run build`。沒有安裝或更新套件。Compose 使用現有 standalone CLI 分別驗證 default／example。

離線證據包含：全新 interpreter audit hook 禁止 socket／DNS／bind，AI import／註冊／Mock 仍成功；另一組子進程完全封鎖 app.ai 匯入、移除 Key 並封鎖外部 DNS／連線，在 flag=false／true 均完成 startup／health／七種 Registry／CRUD／Validate／Manual Execute／History。真實 HTTP／Webhook 的原有測試仍使用受控 Mock，不呼叫外部服務。

### Phase 08A 限制與下一步

- 沒有真實 Provider、SDK／模型 HTTP、Streaming、多模態、Tool Calling、Agent、自動重試、成本追蹤、Secret Manager 或 AI UI。
- Mock 不套用 temperature／max_output_tokens；ProviderConfig 的 enabled／default_model／timeout 不自動生效。沒有 I/O／硬逾時保證，合法 base_url 不代表網路授權。
- Frozen 只是淺層保護；常見敏感 Metadata key 拒絕不是秘密掃描，任意 Prompt／Response 仍可能含敏感文字。ValidationError 的 errors／json 可含原始 input，未來不可直接公開或記錄。
- Registry 只接受可信開發者建立的 Adapter，不是任意 Python 程式碼沙盒。未來節點必須遵守上游權限、Engine 輸出預算及既有 HTTP 安全邊界。
- Phase 08B 的 GitHub 開源發布準備需先評估／補齊 Docker 與遠端 CI 等驗收缺口及既有 P2；本次未自動開始或發布。

正式 data/flowpilot.db 保持 0 bytes、SHA-256 不變；相容性測試只使用隔離資料庫。既有 API／Engine／Schema／DB／前端與依賴檔案另有前後雜湊核對，沒有 Git 初始化、commit、push 或 Release。

## Phase 07B 完成內容

- **FP07B-001：正式前端部署修復**。由 Docker 的 Vite dev 改為多階段 npm ci／production build，最終只有 dist／Node 內建 server，以非 root node 使用者提供靜態資源與固定 `/api` proxy，不含 node_modules／Vite。不新增依賴、Nginx 或其他服務。
- API 代理只採部署者固定的 API_PROXY_TARGET，重寫 Host／移除 Forwarded／hop-by-hop headers，不重試、不設 Execute 短回應逾時；保留 HTTP 200 failed 語意、取消等待結果未知。SPA 直接 URL／refresh、MIME／快取及路徑範圍限制有測試。
- **FP07B-002／FP07A-005：Host 邊界強化**。前後端共享 FLOWPILOT_ALLOWED_HOSTS 精確 JSON 清單，預設 localhost／127.0.0.1／[::1]／backend；拒絕 wildcard、URL、port、未知／畸形 Host，CRUD／Execute 拒絕前無副作用。Host 驗證不等於認證或完整 DNS rebinding 保證。
- Compose 保留單 Backend Worker／Replica、SQLite bind mount、兩個 loopback 埠。新增前端真正 HTML＋代理 healthcheck，後端沿用 Python healthcheck；VITE_API_BASE_URL 改為 build arg，內部 Service Name 不交給瀏覽器。
- 新增唯一 .github/workflows/ci.yml，Push／PR／手動，contents:read，已核實完整 Action SHA，Backend／Frontend／Docker config＋build，不發布。actionlint 通過；遠端執行未測。
- 更新 README 的明確 Repository URL Placeholder、Quick Start、native dev／production、環境配置、工作流與排程教學、安全限制、停止／重啟／備份及 Troubleshooting。未更改真正 .env、執行正式備份或資料操作。
- 沒有新增產品功能、API、Schema、依賴、AI、認證、隊列或分散式能力。沒有大規模重構、Git 初始化／commit／push、Release 或 Image 發布。

### Phase 07B 實際測試結果

| 檢查 | 結果 |
| --- | --- |
| 初始後端／前端 | **591 passed in 6.82s／274 passed，19 files，4.02s** |
| 全新 Python hash 安裝／相容檢查 | **PASS**，隔離 venv 28 個當前平台套件 |
| 全新 npm ci／npm audit | **PASS**，隔離安裝；audit 回應 0 項已知漏洞 |
| 全新安裝環境完整 Pytest | **621 passed in 11.70s**，新增 30 項 Host 回歸 |
| 全新安裝環境 Vitest | **274 passed，19 files，4.68s** |
| Node production server 合約測試 | **12 passed，0 skipped** |
| TypeScript／正式構建 | **PASS**，197 modules，無警告 |
| Host／Config／App GREEN | **46 passed in 0.90s**；RED 原 24 failed／6 passed 已如實記錄 |
| Phase 04／05／Scheduler／History／HTTP 等整合回歸 | **271 passed in 5.21s** |
| 真實 Uvicorn＋production frontend API smoke | **PASS**，CRUD／Validate／Execute／History／Detail、failed／skipped／422／404、Host 無副作用與空 Allowlist |
| 真實瀏覽器操作 | **PASS**，建立／連線／保存／Reload／Open／Run／Result／History、Schedule 啟停、直接 URL、Backend outage／恢復及 HTTP 200 failed |
| 後端進程重啟／SQLite／Schedule 恢復 | **PASS**，PID 改變、Definition／History 保留、running→interrupted、真實 Cron 派發一次、再次重啟不重放 |
| Compose default／.env.example、uv lock、語法 | **PASS** |
| actionlint 1.7.12 | **PASS**，官方校驗和核對；ShellCheck／Pyflakes 未執行 |
| Docker build／startup／container recreation | **NOT_TESTED：DOCKER_UNAVAILABLE** |
| 遠端 GitHub Actions | **NOT_TESTED**，沒有 Git／Push／workflow run |

初次離線安裝因 cache 缺包失敗，沒有視為通過；以現有 hash／lockfile 從官方 registry 在新隔離目錄安裝後成功，未升級套件。npm audit 與 Python 相容檢查不是完整 Python／容器 CVE 審計。

最終 Pytest 使用全新安裝：backend 目錄執行 `..\.tools\phase07b-install\backend\Scripts\python.exe -m pytest --basetemp=.pytest_cache/phase07b-clean-install -q --tb=short`。前端使用全新 npm ci 的來源複本執行 test／test:server／typecheck／build。完整路徑與其餘命令見 Release Readiness。

### Phase 07B 資料安全與剩餘工作

全部測試使用獨立 DB／production runtime／pytest 目錄。正式 data/flowpilot.db 仍為 0 bytes，前後 SHA-256 相同；最終測試 DB 沒有 running、排程為 Disabled，臨時頁面及進程已關閉。沒有外部 Webhook／通知或真正 API Key。

仍待 Docker Engine 環境的完整 build／up／健康／volume／container recreation／Linux 權限，以及實際遠端 CI。保留 P2：FP07A-002 大整數配置阻擋列表、003 舊結果節點選取、004 極端 offset 500；005 已補 Host 限制。還有同步 Execute 結果未知、歷史非完整快照、遮罩有限、單進程 Scheduler 及未驗證真實外網 TLS 等既有限制。

上述部署／CI 缺口仍需補驗；Phase 08A 已另經授權完成獨立 Foundation，不代表已可 Release。Phase 07B 真實畫面：[Production workflow smoke](images/production-workflow-smoke.jpg)。

## Phase 07A 審查與修復

- 已閱讀現有規範、README／架構、依賴／lockfile、測試及容器配置。沒有 `.git`，無法用 Git 判定未提交修改；沒有初始化、reset、clean、commit、push 或刪除無關檔案。
- 審查 API／Schema／Registry／Validation、Engine／Condition／七種 Executors、HTTP／Webhook 安全、Scheduler／OS lock／Execution Service、SQLite／History、Dashboard／Editor／Adapter／API Client／Execution／History／Schedule UI。
- **FP07A-001（P1，已修復）**：History 曾將長 Node ID 截為 256 字元，造成不同節點身份碰撞與 Detail 無法載入。現在保留完整 ID，超限以省略完整摘要或 nullable 錯誤參照處理，仍保留大小限制及 history_truncated；不改 Live Result。新增 2 項回歸並先重現失敗。
- **FP07A-002（P2，未修復）**：API 建立的合法大整數配置會使整個 Dashboard／Open 列表失敗；正常工作流可用 `/editor?id=<UUID>` 直接開啟，大型識別碼應使用字串。不能直接移除編輯精度保護。
- **FP07A-003（P2，未修復）**：刪除執行過的節點後，畫布的另一個選取會阻止結果面板查看該舊節點詳情；可清除畫布選取或查看獨立 Historical Detail。
- **FP07A-004（P2，未修復）**：History offset 超出 SQLite int64 回傳安全 500，應為 422；UI 正常分頁不受影響，服務仍可回應 health。
- **FP07A-005（原 P2，Phase 07B 已強化）**：當時 API 接受任意 Host；目前已加入前後端精確清單與拒絕前無副作用測試。完整 DNS rebinding 瀏覽器利用未驗證，CORS／Host 都不是認證。
- 不回填舊版本已截短的歷史，避免猜測節點身份或改寫既有資料。正式 data/flowpilot.db 保持 0 bytes，前後 SHA-256 相同。

### Phase 07A 實際驗證

| 檢查 | 結果 |
| --- | --- |
| 初始完整後端／前端 | **589 passed in 8.66s／274 passed，19 files，7.99s** |
| 初始 TypeScript／Build | 通過 |
| 新增 Bug 回歸 RED | **2 failed**，正確重現，未視為通過 |
| 修復後 History／Execution Service | **36 passed in 1.00s** |
| Scheduler／History／Service 相關回歸 | **62 passed in 1.74s** |
| 最終完整 Pytest | **591 passed in 8.94s** |
| 最終完整 Vitest | **274 passed，19 files，4.53s** |
| 最終 TypeScript／Build | **通過**，197 modules，無警告 |
| Engine／HTTP／Data 既有專項 | **247 passed in 0.76s** |
| 固定種子 DAG 獨立對照 | **400 個 2–30 節點圖通過**，最多一次／啟動分支／直接 input／成功祖先 |
| 真實 Uvicorn／Vite／APScheduler smoke | **通過**：health、CRUD／Validate／OpenAPI、Manual、長 ID History、Scheduler 派發、代理、重啟恢復與停用／刪除 |
| Compose default／.env.example、uv lock offline | **通過**，配置及依賴未修改 |
| Docker build／容器執行 | **未執行**，沒有 Engine／Desktop |
| 完整瀏覽器 E2E／CI | **未執行**，完整 E2E 留待 07B；Repository 沒有既有 CI |

完整最終命令：backend 執行 `.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest_cache/phase07a-final -q --tb=short`；frontend 執行 `node .tools/npm11/package/bin/npm-cli.js test`、`node .tools/npm11/package/bin/npm-cli.js run typecheck`、`node .tools/npm11/package/bin/npm-cli.js run build`。其他基準、RED／GREEN 與 smoke 命令詳見 Audit Report。

初次受限沙箱執行未完成／快取拒絕存取，以及 smoke 腳本的首頁等待超時／誤用 GET Validate，均未標為通過；修正執行環境／腳本後重跑成功。沒有更改產品或降低安全限制來通過測試。所有臨時服務已關閉，沒有外部 HTTP 或正式資料操作。

### 原 Phase 07B 建議的承接狀態

本次已承接 production serving、Host、CI、完整本地回歸與最小真實瀏覽器／重啟驗證。Docker／Linux volume、遠端 CI 及真實外網 TLS 尚未驗證，現況以上方 Phase 07B 與 Release Readiness 為準。

## Phase 06B 功能基礎（保留）

**Phase 06B：Workflow Dashboard & Execution Integration 已完成。** 保留 Phase 01–06A，在現有 React Flow Editor、API Client 及後端契約上整合 Dashboard、Manual Run、驗證、節點最終狀態、結果／歷史詳情及排程管理。以下是該階段的功能與驗收記錄；本次 History 修復見上節。

## 已完成 UI

- `/` 為 Dashboard，列表呈現名稱、描述、Trigger、節點數、UTC 更新時間；建立、Open Editor、Refresh、刪除確認及 409 錯誤均重用既有 CRUD Client。
- `/editor` 保留唯一的 Phase 06A 編輯器，`/editor?id=<UUID>` 可直接載入工作流；`/home` 保留原首頁及 health。
- Toolbar 新增 Run Workflow 與 Dashboard 導航；保留 New／Open／Save／Delete／Validate、Explicit Save、JSON 緩衝及未保存提示。
- Inspector 提供 Properties／Execution／History／Schedule／Validation，依需載入；History／Schedule 首次開啟後保留元件狀態，Save／Run 更新時重新讀取，沒有持續輪詢或大量 Dashboard 每列額外查詢。
- Run 僅執行已保存、無未保存修改、恰有一個 Manual Trigger 且沒有 Schedule Trigger 的工作流。未保存時提示先 Save；Schedule 顯示專用說明，不改 Trigger，也不提供 Schedule Run Now。
- Run 先檢查一般圖形 Validation，通過後送 Execute，後端再做 Executor／配置 readiness。Validation 失敗不妨礙保存合法 Draft；錯誤與警告可見，Node ID 提供 Locate 操作。
- 執行請求不使用一般 API 的 10 秒短逾時、不自動重試，以同步 ref 防止重複提交。驗證中與 Running 分開，未收到結果不假裝成功；HTTP 200 的 failed 顯示 Failed。
- 結果收到後按 node_id／execution_id 呈現 pending／running／success／failed／skipped；有文字與圖示，未知狀態合理降級，沒有即時逐節點動畫或 WebSocket。
- Execution Panel 顯示 ID、工作流、Trigger、UTC 起迄、Duration、節點統計與安全錯誤；選取節點查看輸出及詳情。結果保留當次工作流／節點名稱快照。
- 工作流修改後清除舊徽章，結果明示屬於先前保存版本；重載／切換以 ID、epoch、revision 及 AbortSignal 防止舊請求污染新工作流。保存期間改選取不覆蓋選取，原 Phase 06A 行為保留。
- History 使用 limit=20／offset、狀態篩選及手動 Refresh；成功或 failed 完成皆刷新已載入的歷史。資料保留清理令分頁超界時，自動重新查詢有效頁面。
- Historical Detail 獨立查詢及呈現，不套用畫布徽章，不以目前節點名稱冒充歷史名稱；明示後端沒有完整歷史 Workflow Snapshot。
- Schedule 狀態、Cron、Timezone、Next Run 及 scheduler_running 全部採後端回應。啟用需已保存且 clean，停用既有 Job 可在 dirty 或移除 Trigger 的 Draft 中進行。
- 啟停無樂觀狀態更新，失敗保留前次已確認結果；Save 後重新取得排程狀態，反映後端自動停用。Save／Toggle 交錯時延後 GET，避免舊回應覆蓋狀態。
- 結果及 Output 只保存在記憶體，顯示前額外遮罩常見敏感欄位／憑證文字並限制大小；不寫 LocalStorage、不輸出完整結果至 Console。歷史 output=null 顯示指定缺失提示。
- 更新 README、ARCHITECTURE、AGENTS 及本文件，新增 Dashboard／Execution／Schedule 真實驗收截圖。

## 主要組件與 API 檔案

| 檔案 | 職責 |
| --- | --- |
| frontend/src/pages/DashboardPage.tsx | 工作流列表與共用 CRUD 操作 |
| frontend/src/pages/WorkflowEditorPage.tsx | 原有 Editor 加入操作整合與 Inspector |
| frontend/src/hooks/useWorkflowExecution.ts | Run／Validate 流程、互斥及版本隔離 |
| frontend/src/components/execution/ExecutionStatus.tsx | 狀態文字、圖示及顏色 |
| frontend/src/components/execution/ExecutionPanel.tsx | 即時／歷史結果與節點詳情 |
| frontend/src/components/execution/ExecutionHistory.tsx | 分頁、篩選、Refresh、Detail |
| frontend/src/components/execution/ValidationPanel.tsx | 一般圖形／readiness 錯誤及定位 |
| frontend/src/components/schedule/SchedulePanel.tsx | 排程唯一前端狀態、啟停及 Next Run |
| frontend/src/components/workflow/WorkflowNode.tsx | 按 Node ID 呈現結果徽章 |
| frontend/src/components/workflow/WorkflowToolbar.tsx | Run 與導航 |
| frontend/src/services/workflowApi.ts | 可重用 requestJSON、統一安全錯誤及取消 |
| frontend/src/services/executionApi.ts | Execute／History／Detail |
| frontend/src/services/scheduleApi.ts | Schedule GET／PUT |
| frontend/src/types/execution.ts、types/schedule.ts | 真實後端契約 |
| frontend/src/utils/executionDisplay.ts | 安全摘要、額外遮罩、有界 JSON Viewer、UTC 格式 |

## 已整合 API

| 方法 | 路徑 | 用途 |
| --- | --- | --- |
| GET | /api/health | Dashboard／Editor 連線狀態 |
| GET | /api/node-types | 保留 Registry Library |
| GET／POST | /api/workflows | 列表／保存新工作流 |
| GET／PUT／DELETE | /api/workflows/{id} | 載入／保存／刪除 |
| POST | /api/workflows/{id}/validate | 一般圖形結構及 readiness，非完整 Executor 準備度 |
| POST | /api/workflows/{id}/execute | 同步 Manual 執行，後端嚴格 readiness |
| GET | /api/workflows/{id}/executions | 歷史分頁與狀態篩選 |
| GET | /api/executions/{execution_id} | 歷史詳細資料 |
| GET／PUT | /api/workflows/{id}/schedule | 權威狀態及啟停 |

一般請求 10 秒，Execute 僅使用呼叫端 AbortSignal。404／409／422／503／取消／網路錯誤／無效回應有對應訊息；422 使用已知代碼的摘要及定位 ID，不顯示原始 input／ctx／traceback。API 回應先做格式與工作流／Execution ID 驗證。

## Phase 06B 實際測試結果

| 檢查 | 結果 |
| --- | --- |
| 最終完整前端 Vitest | **274 passed，19 個測試檔，4.01s** |
| Phase 06A 回歸 | 既有 143 項保留通過；新增 131 項 API、元件、操作及 Hook 測試 |
| 獨立 TypeScript | **通過**，npm run typecheck |
| 正式構建 | **通過**，npm run build，197 modules，無警告 |
| 後端 Pytest 回歸 | **589 passed in 7.71s，無警告** |
| Compose default／.env.example config | **通過**，官方 standalone Compose 5.6.0，兩次 exit 0 |
| uv lock --check --offline | **通過**，原後端 30 個套件鎖定未變 |
| 真實瀏覽器＋Uvicorn＋Vite | **通過**，Dashboard／Editor／Execute／History／Schedule 下述流程 |
| 真實 Scheduler 派發 | **通過**，瀏覽器關閉後受控推進到期時間，APScheduler 自行執行並保存 schedule success |
| Lint | 原專案沒有 Lint script／配置，未執行亦未聲稱通過；TypeScript strict／noUnused 已檢查 |
| Docker image／容器執行 | **未執行**，沒有 Docker Engine／Desktop |

前端指令：`npm test`、`npm run typecheck`、`npm run build`，使用專案已記錄的 npm 11.21.1 本地 CLI。沒有更換 Package Manager 或加入測試平台。

後端指令：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest --basetemp=.pytest_cache/phase06b-regression -q --tb=short
```

主要新增測試涵蓋：未保存／dirty 阻擋、Manual／Schedule 限制、重複 Run、HTTP 200 failed、409／422／503、驗證未提交前的網路錯誤、Node ID 對應、修改後清徽章、舊請求／重載隔離、Snapshot 名稱、History／Detail／篩選／分頁／Retained data shrink、Schedule failure／Save race／UTC、Dashboard no-N+1、敏感內容遮罩及直接 URL 載入 Metadata 競態。

## 實際瀏覽器驗收

測試使用獨立 .tools/ SQLite、127.0.0.1 Uvicorn／Vite、正式既有 Engine／Scheduler／History。HTTP 節點使用 Mock Transport 與受控 DNS，沒有真實外部請求：

1. Dashboard 空狀態 → Create Workflow → 添加 Manual Trigger、HTTP Request、Logger → 移動與 Handle 連線 → 配置 URL → Save。
2. Run 執行成功，顯示 Success、Duration、三節點成功徽章與相應 Node ID。HTTP 回應中的測試 authorization 值顯示為 [REDACTED]。
3. History 自動／首次載入查到同一 Execution ID，View Details 獨立顯示；預設歷史 output=null 顯示 Output not stored or unavailable，畫布不被歷史覆蓋。
4. 修改 HTTP URL 後舊徽章清除，Run 提示先 Save；Save 後執行受控 HTTP 500，整體 Failed，Manual success、HTTP failed、Logger skipped，未誤判 HTTP 200 為成功。
5. New → Schedule Trigger／Logger → Cron 配置 → Save。Manual Run 顯示排程專用提示，沒有調用 Manual Execute。
6. Schedule GET 顯示 Disabled；Enable 後顯示後端確認的 Enabled 與 Next Run UTC，沒有前端 Cron 計算。
7. 關閉瀏覽器後，將測試 Job 的 next_run_time 推進至現在，真實 APScheduler 執行成功並持久化；重新以 /editor?id=... 載入後，History 可查到 schedule success。
8. Disable 後顯示 Disabled／No next run scheduled。再次 Enable，改為無效 Cron Draft 並 Save，UI 重新取得 SCHEDULE_INVALID_WORKFLOW 自動停用狀態。
9. 嘗試啟用無效 Cron，422 顯示安全錯誤與 Locate node；最後修復 Cron 並保存，維持 Disabled。
10. 390×844 窄螢幕確認 Dashboard／New／Open／Save／Validate／Delete／Run 皆換行可見；工作區維持橫向可操作。
11. 返回 Dashboard 顯示兩個已保存工作流及對應 Editor 連結；瀏覽器未捕獲 warning／error。
12. 真實 API 再核對成功／失敗／skipped、歷史隱私、Schedule 歷史及 Disabled／next_run_at=null；Definition 沒有 executionStatus 或其他 UI 欄位。

臨時頁面與伺服器已關閉。根目錄 data/flowpilot.db 仍為原有 0 bytes，前後 SHA-256 相同；沒有修改正式資料。測試腳本／證據留在被忽略的 .tools/，不是應用路由、額外引擎或產品 API。

截圖：[Dashboard](images/workflow-dashboard.jpg)、[Execution](images/workflow-execution.jpg)、[Schedule](images/workflow-schedule.jpg)。截圖中的外部 HTTP 資料來自受控 Mock。

## 已知限制

- 同步 Execute 沒有 WebSocket／逐節點進度；請求期間只能顯示整體 Running，完成後展示最終節點結果。
- 取消等待、切換頁面或網路中斷不等於取消後端。結果未知時應查歷史，沒有自動重試；尚無後端 Cancel API。
- 歷史只有 Definition Hash 與安全節點摘要，不是完整圖形快照；不能將歷史名稱／配置或結果視為目前版本。
- 基本前端遮罩不能辨識所有文字秘密。輸出只在記憶體、有界顯示；後端預設仍不保存輸出。
- Dashboard 不顯示列表 API 未提供的最新執行／Schedule 狀態，於 Editor 內查詢，避免無界 N+1。
- 下次執行時間明確展示 UTC，另列 Schedule Timezone；沒有第二套 Cron 計算、完整 Cron Builder 或自動 Run Now。
- 保留 Phase 06A 的桌面 Drag and Drop／點擊新增、窄螢幕橫向工作區、未知配置只讀與安全整數限制；沒有 Undo／Redo 或 LocalStorage 草稿恢復。
- 後端仍為單進程 Scheduler／SQLite，沒有跨進程 Exactly-Once。既有 HTTP Allowlist／DNS／大小／逾時與歷史保留限制繼續適用，不宣稱完整 SSRF 審計或網路沙盒。
- 沒有修改依賴或後端核心；Docker 配置可解析，映像建置與 Linux 容器連線尚未驗證。

## 後續階段範圍

Phase 08A 已完成，完整發布驗收仍 NOT_READY，等待 Docker／遠端 CI 補驗證與 Phase 08B 指示。後續不自動加入真實 AI／節點、認證、協作、WebSocket、重試引擎或發布能力。

未執行 Git commit、push、發布、部署或 Git Repository 初始化。

