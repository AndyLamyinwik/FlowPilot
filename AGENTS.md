# FlowPilot 開發規範

FlowPilot 是輕量級、可視化、可自行部署的開源自動化工作流平台。優先保持簡單、可理解、可測試和可維護的架構。

## 技術與範圍

- 前端使用 React、TypeScript、Vite 和 Tailwind CSS。
- 後端使用 Python 3.12+、FastAPI、Pydantic 和 SQLite；容器使用 Docker Compose。
- 目前授權範圍為 Phase 09：保留 Phase 01–08B，進行 v0.1.0 最終驗收。使用者後續明確要求將完整原始碼先上傳 GitHub，已另行授權現在 commit／push 已審查的原始碼、測試、配置與文件，不以本機缺少 Docker 阻擋原始碼公開。正式 v0.1.0 tag／GitHub Release 仍需對應 Commit 的必要 CI、Docker 驗收與其他發布條件通過，不能直接修改 Checklist 繞過。只允許與發布直接相關的小型修正或驗收，不新增產品功能、不改引擎／Scheduler／Schema／前端、不升級依賴樹。
- 使用者於 2026-10-30 另行明確批准 FP07A-002 發布前小修：僅調整前端列表摘要邊界及相關型別／測試，避免合法 API 匯入的超大整數配置阻擋整份 Dashboard／Open 列表；保留完整工作流載入、編輯和保存的嚴格數字精度檢查。這是上一條「不改前端」的單項例外，並已授權測試及精確 Commit CI 通過後繼續 tag／Release；不擴大至其他前端功能或既有 P2 修復。
- 使用者已明確同意建立 AndyLamyinwik/FlowPilot 公開倉庫並保留 ChatGPTBot 自動連接；倉庫已建立，名稱為 FlowPilot，不追加 Bot 名稱。使用者也已另行同意啟用 GitHub Private Vulnerability Reporting 及設定頁所述唯讀安全分析權限，該項已啟用；這兩項具體授權持續有效，不重複詢問。其他掃描／AI／自動修復與帳號整合設定不在此授權內。倉庫建立與正式發布的驗收條件分開，Docker runtime／對應 Commit 的遠端 CI 等未通過時仍不得發布。
- 不得提前實作後續能力，包括真實 AI Provider／SDK／HTTP 請求、AI Node Executor／Agent／Tool Calling／Streaming、模型下載、WebSocket／即時節點動畫、Undo/Redo 系統、認證、多使用者、Incoming Webhook、分散式排程、背景隊列、任意程式碼/Shell 節點、重試配置 UI、Secrets UI、版本控制、插件市場或自動發布流程。不得更改既有 Repository Visibility、改寫 Git History、Force Push、覆蓋既有 Tag、繞過 Branch Protection、刪除其他 Release 或發布 Docker Hub Image。
- 未使用的擴展位置保留目錄或文件說明即可，不建立無用途的抽象、介面或依賴。

## 修改原則

- 開始前檢查既有檔案和相關文件；保留無關內容，不無故破壞或刪除已存在的功能。
- 採取模組化開發：API 路由負責 HTTP，core 負責配置和日誌，db 負責資料庫生命週期與 Repository，services 負責驗證與業務規則，models 放資料庫記錄，schemas 定義 Pydantic API 契約。
- 資料庫記錄與 Pydantic API Schema 分離；維持目前 sqlite3 架構，SQL 使用參數化操作，資料表初始化不得刪除既有資料。
- 結構完整性與執行準備度分開驗證。保留 Phase 02 Draft 保存原則及圖形驗證語意；手動執行要求單一 Manual Trigger，定時執行要求單一 Schedule Trigger，兩種入口不可混用，並須通過目前 Executor 能力與配置檢查。
- 節點 Registry 只管理 Metadata，不包含節點執行邏輯。config 必須是合法 JSON，不得保存明文密碼、API Key 或其他密鑰。
- AI Provider 模組獨立於 FastAPI Request、Workflow DB／Context 與 Scheduler；只使用統一 AI Request／Response／錯誤。Registry 不存密鑰、不動態載入模組，Mock 僅供明確的開發／測試使用，不自動註冊成節點或公開 API。FLOWPILOT_AI_ENABLED 預設 false，設 true 也不代表已有真實 Adapter。不得預設保存 Prompt／Response 或執行模型生成的操作。
- 執行引擎只協調依賴、狀態與資料傳遞；節點業務邏輯放在獨立 Executor。每次執行建立獨立 Context，不共享可變狀態。
- 節點 input_data 維持直接來源 Node ID 對應完整輸出，僅包含啟動且成功的上游。ancestor_outputs 額外提供當次執行中沿啟動路徑成功的祖先資料；不得跨工作流或讀取無關節點。
- 必須等待所有上游狀態確定；至少一條上游路徑啟動且成功則執行，全部未啟動則 skipped。Condition 僅啟動 true/false 對應連線；普通跳過不是失敗。維持確定性拓撲順序、每節點只執行一次。
- 採 fail-fast；前置條件錯誤回傳 422，已開始的節點失敗回傳 HTTP 200 的 failed 執行結果，尚未執行節點標記 skipped。
- 不使用 eval、exec、任意模組載入、Shell 或本地檔案操作來解讀 config；不把環境變數或秘密放入 Context、日誌或錯誤回應。維持執行節點數與輸出資料量限制。
- HTTP 與 Outgoing Webhook 共用安全 Client：預設空的明確 Host Allowlist、HTTPS、封鎖非公開位址、驗證 DNS 並固定連線目標、停用 redirect/環境 proxy、逾時及大小上限。不得在工作流存放 Authorization、Cookie 等憑證 Header。
- Readiness 檢查不得發出 HTTP 請求或依賴外部服務。HTTP 測試使用 Mock Transport 與受控 DNS resolver，不以真實外部服務為測試依賴；文件不得誇大 SSRF 防護保證。
- 手動與定時執行都經過同一個 Execution Service、Engine 和 Node Executors；Workflow 層級互斥必須以 finally 釋放，不得在執行期間持有 SQLite 寫入交易。
- Cron 與 Timezone 只保存在 Workflow Definition；Schedule Metadata 保存 enabled 等管理狀態。APScheduler 使用記憶體 Job Store，從 SQLite 恢復，不建立第二份 Cron 資料來源。
- 預設單一後端進程、一個 Scheduler、Uvicorn workers=1、不使用 production reload；啟動恢復 interrupted 前先取得資料庫的 OS instance lock。不得宣稱分散式或跨進程 Exactly-Once。
- 歷史預設不持久化節點輸出、輸入或完整配置；選擇保存輸出時須遮罩常見敏感欄位並限制記錄大小。歷史清理不得刪除 running 或未完成記錄，重啟不自動重放外部副作用。
- 前端頁面負責呈現，services 封裝 API，types 定義共享資料型別，components 放可重用 UI。
- React Flow 的 UI Node type 與業務 Node type 分離，以 Adapter 往返轉換；保留 ID、config、position、schema_version 及兩端 Handle，禁止序列化選取、尺寸等畫布 UI 狀態或丟棄未知節點配置。
- Node Library 以後端 Registry 為可用性來源。前端拒絕新建循環、自連線、重複連線、Trigger 上游及非法 Condition Handle；後端驗證仍為最終權威，既有合法 Draft 不因缺少執行配置而無法保存。
- 配置只更新本地 React State，點擊 Save 才呼叫保存 API。無效 JSON 暫存不得遺失或假裝已保存；切換工作流及離開頁面時提示未保存變更。選取、縮放及平移不得標記為資料修改。
- Run 與啟用排程只能使用已保存且無未保存修改的版本；Manual Execute 不執行 Schedule Trigger。/validate 的一般圖形結果不等同 Executor readiness，必須處理 Execute／Schedule 的 422。
- 同步 Execute 不使用一般 API 的短逾時，不重複送出或自動重試；HTTP 200 的 failed 結果仍是執行失敗，網路中斷則結果未知，不可假裝工作流失敗或成功。
- 執行狀態按 node_id 與 execution_id 對應，只作畫布呈現，不保存至 Definition；修改、重載或切換工作流清除版本關聯。歷史詳情不覆蓋目前畫布、不宣稱擁有完整歷史圖形快照。
- 排程狀態與 Next Run 以後端確認結果為準，Save 後重新取得以反映自動停用；歷史分頁及手動刷新，不持續輪詢，也不對 Dashboard 每列無限制查詢。
- 執行輸出僅保存在當前記憶體，顯示前額外遮罩常見敏感欄位並限制 Viewer 大小，不寫入 LocalStorage 或 Console；不宣稱基本遮罩能辨識全部敏感資訊。
- 只增加有明確需求的依賴。固定直接依賴版本並同步更新 lockfile；勿手動拼造 lockfile。
- 不將 API 主機位址硬編碼到業務程式碼；以環境變數配置。`VITE_*` 會傳送至瀏覽器，不得放入密鑰。
- 正式前端由 dist／Node 內建服務提供，不以 Vite dev／preview 當正式服務。VITE_API_BASE_URL 是 build-time 設定；API_PROXY_TARGET 只在伺服器端使用，代理固定目標、不重試、不設 Execute 短回應逾時。維持靜態路徑範圍與前後端精確 Host 清單，不能以 Forwarded Header 改寫信任邊界。
- GitHub Actions 維持單一 CI、最小唯讀權限與已核實的完整 Action SHA；本地檢查與遠端執行分開記錄，沒有明確授權不加入發布流程。
- 預設服務只綁定本機；SQLite、`.env`、密鑰、日誌和本地快取不得提交。
- 未經使用者明確要求，不進行 Git commit、push、發布或部署。

## 驗證與交付

- 每次修改後執行與變更相關的測試。後端使用 Pytest；前端執行基本測試、TypeScript 檢查和構建驗證；修改正式前端服務時執行 npm run test:server。
- 修改 Compose 或 Dockerfile 時執行 `docker compose config`；環境具備 Docker 時執行容器構建及連線驗證。
- 涉及 API 配置或代理時，除了模擬測試，也應盡可能實際啟動前後端，確認 `/api/health` 連通。
- 只把實際執行且通過的檢查列為通過；工具不可用、未執行或失敗的部分必須清楚記錄。
- 完成任務後更新 `docs/PROJECT_STATUS.md`，記錄完成內容、限制、測試結果及下一階段建議。配置或架構變動時同步更新 README 與架構文件。
- 完成已授權階段後停止，等待下一階段指示。

