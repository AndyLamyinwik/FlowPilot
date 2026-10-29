# AI Provider Guide

## Overview

Phase 08A 建立獨立、可測試的文字 AI Provider 契約，讓未來 Adapter 可以使用共同的 Request／Response／錯誤格式。**FlowPilot V1 不需要 AI；目前沒有真實模型整合、AI Workflow 或公開 AI API。**

模組位於 `backend/app/ai/`，只依賴 Python 標準庫及既有 Pydantic。它不依賴 FastAPI Request、Workflow Database／Schema、Execution Context 內部結構、Scheduler 或前端。應用啟動不匯入此模組，也不建立 Provider Registry。

## Current Status

- 唯一實作為開發／測試用 **MockAIProvider**，不呼叫模型、不讀取 Key、不下載模型或使用網路。
- Registry 每個實例起初為空，需由可信 Python 程式明確註冊；沒有 Factory、動態模組載入、自動發現或全域啟用。
- `FLOWPILOT_AI_ENABLED=false` 為預設。設為 true 只記錄未來的啟用意圖，不會註冊 Provider、建立 AI 節點／路由或開始真實模型呼叫。
- Workflow JSON version 1、原七種節點、Engine、Condition、Scheduler 及 React Flow UI 不變。
- Phase 07B 的 Docker／遠端 CI 驗收缺口仍存在；本階段完成不代表專案已 Release Ready。

## Provider Interface

採用唯一的同步 `AIProvider` Protocol：

```text
provider_id: str
provider_name: str
capabilities: AIProviderCapabilities
generate(request: AIRequest) -> AIResponse
```

Adapter 身份須穩定；`provider_id` 格式為 `[a-z][a-z0-9_-]{0,63}`。能力 Metadata 目前包含 `is_mock`、`supports_temperature`、`supports_max_output_tokens`，只表達支援情況，不實作 Sampling 或 Token 限制。

新的可信 Adapter 應接受已驗證 AIRequest、返回已驗證 AIResponse，並將供應商的例外轉為安全 AIProviderError。不要修改 Engine，或為不同供應商建立第二套同步／非同步接口；未來非同步／Streaming 語意須另行設計及授權。

## Request Schema

| 欄位 | 契約 |
| --- | --- |
| model | 必填非空白文字，去除頭尾空白；目前只是 Adapter 使用的標籤 |
| messages | 必填非空陣列，每項為 AIMessage |
| message.role | system／user／assistant |
| message.content | 必填非空白文字，保留原有頭尾空格及換行，不自動重寫 Prompt |
| temperature | 預設 null，代表未指定；有值時為有限數值 0–2，拒絕 bool／字串／NaN／Infinity |
| max_output_tokens | 預設 null，代表未指定；有值時為嚴格正整數，不接受 bool／小數／數字字串 |

模型參數不是所有供應商的共同保證。範圍驗證不等於特定模型接受該參數；未來 Adapter 負責能力與模型差異。Mock 只驗證格式，**不套用 temperature／max_output_tokens**，沒有真實 Sampling／Token Budget。

所有 AI Schema 拒絕未知欄位，採嚴格型別及有效 Unicode。沒有 Tool／Function Calling、Vision、Audio、Video、Reasoning Controls 或多模態結構。

## Response Schema

| 欄位 | 契約 |
| --- | --- |
| provider | Provider ID |
| model | 回應模型標籤，非空白文字 |
| content | 文字，可為空；不接受 Client、Exception 或任意 Python 物件 |
| finish_reason | 可省略／null，或非空白文字；不把各供應商綁死到共同 enum |
| usage | AIUsage 或 null，預設 null |
| usage.input_tokens／output_tokens／total_tokens | 各自可省略／null，或嚴格非負整數；不補算、不猜測精確數值 |
| metadata | 預設空物件，只接受有限 JSON，最多 32 層容器，拒絕循環與常見憑證欄位 |

可用 `model_dump(mode="json")` 或 `model_dump_json()` 轉換。Partial usage 不會自動計算 total；Mock 的 usage 為 null，避免讓測試數字冒充真實 Token 統計。

Model 設為 frozen，但 list／dict 不是深度不可變。呼叫端應維持資料契約；Mock 會重新驗證 AIRequest，並為每次回應建立獨立物件，不保留 Prompt。Registry Metadata 也以獨立快照回傳。

## Registry

`AIProviderRegistry` 提供：

- `register(provider)`：驗證同步介面與公開 Metadata，拒絕同 ID 重複註冊，不呼叫 generate。
- `get(provider_id)`：取得已註冊 Adapter；合法但不存在的 ID 拋出 AIProviderNotFoundError；格式不合法則為 AIProviderConfigurationError。
- `list_providers()`：按註冊順序回傳公開 AIProviderMetadata 快照，沒有 Adapter 內部屬性、設定或憑證。

Registry 只由可信後端程式組合，不接受工作流指定 Python 模組。Provider 物件由開發者建立，Registry 本身沒有 Key 欄位或 Credential Store。註冊應在使用前完成，本階段不提供並行 Registry 寫入協調。

## Configuration Strategy

`app.core.config.Settings.ai_enabled` 對應 `FLOWPILOT_AI_ENABLED`，預設 false，`.env.example` 與 Compose 同步記錄。它與 `AIProviderConfig` 分開：前者是應用啟用意圖，後者是未來單個 Adapter 的資料契約；目前都不觸發模型執行。

| AIProviderConfig 欄位 | 預設／規則 |
| --- | --- |
| provider_id | 必填合法 Provider ID |
| default_model | null；有值時非空白文字 |
| enabled | false，嚴格布林 |
| timeout | 30 秒，有限數值，0 < timeout ≤ 300 |
| base_url | null；有值時僅驗證 HTTP(S) 語法，拒絕憑證、query、fragment、控制字元與無效 hostname／port |

Config 不從 Key 環境變數建立憑證，也不接受 api_key／credentials 等額外欄位。`default_model` 不會自動填進 AIRequest；`enabled` 不會自動註冊或攔截直接 Mock 測試；`timeout` **尚未實作 I/O 或硬逾時**。

base_url 合法不代表可以連線，沒有 DNS、HTTP 或網路授權效果。即使語法可表達未來本機 Ollama endpoint，也必須另行設計明確網路政策，不能藉此放寬既有 HTTP／Webhook 限制。

## Mock Provider

正常回應的 content 固定為 `Mock response: no AI model was called.`，provider 為 mock、model 保留請求標籤、finish_reason 為 stop、usage 為 null、metadata 為 `{"mock": true}`。不同 Prompt 不會觸發推理或改變固定文字。

`MockAIProvider(simulate_error=True)` 是可信測試程式的建構參數，用來拋出固定 AIProviderError。它不是 Request 欄位、工作流配置或錯誤觸發 API。Mock 沒有外部 SDK、隨機結果、日誌、副作用或自動保存。

## Example

在 `backend/` 的既有虛擬環境執行以下 Python；不需要 Key 或網路。輸出只展示固定 Mock，不能當作真實模型內容或 Production Prompt／Response 日誌：

```python
from app.ai.exceptions import AIProviderError
from app.ai.providers.mock import MockAIProvider
from app.ai.registry import AIProviderRegistry
from app.ai.schemas import AIMessage, AIRequest

registry = AIProviderRegistry()
registry.register(MockAIProvider())
request = AIRequest(
    model="mock-model",
    messages=[AIMessage(role="user", content="Offline architecture check")],
)
response = registry.get("mock").generate(request)
assert response.provider == "mock"
assert response.usage is None
assert response.metadata == {"mock": True}
print(response.model_dump_json(indent=2))

try:
    MockAIProvider(simulate_error=True).generate(request)
except AIProviderError as error:
    assert error.code == "AI_PROVIDER_ERROR"
else:
    raise AssertionError("Expected a simulated provider error")
```

建議將此片段存成 backend 內的本地檔案，再以 `.venv\Scripts\python.exe <檔名>`（Windows）或 `.venv/bin/python <檔名>` 執行。驗收時也會直接執行文件中的同一片段。

## Error Handling

使用簡單的共同基底及固定安全訊息：

| 類型 | 用途 |
| --- | --- |
| AIProviderError | 一般 Provider 執行失敗／Mock 模擬失敗 |
| AIProviderNotFoundError | 查找未註冊 Provider |
| AIProviderConfigurationError | 配置／介面／ID／重複註冊／無效請求 |
| AIProviderTimeoutError | 預留未來 Adapter 的逾時轉換 |
| AIProviderRateLimitError | 預留未來供應商限流轉換 |
| AIProviderResponseError | 預留未來無效回應轉換 |

錯誤只包含固定 code／public_message，沒有接受任意供應商文字的建構參數。未來 Adapter 應以安全錯誤替代原始 exception，避免把 Key／Header／Prompt／traceback 傳給呼叫端。不提供重試、限流 Queue 或成本追蹤。

Pydantic 輸入錯誤仍為 ValidationError；`hide_input_in_errors=True` 隱藏其文字格式中的 input，**不代表 `.errors()` 或 `.json()` 中的 input／ctx 已被移除**。本階段沒有 AI API；未來公開錯誤邊界必須使用受控代碼與訊息，不能直接傳回或記錄原始驗證資料。

## Future Integration

OpenAI、Anthropic、Gemini、Ollama 及 Custom Provider 都應由可信開發者按相同同步 Protocol 實作，再顯式 register；本階段沒有為它們建立空白類別、SDK、HTTP Client、端點或模型下載。

未來 Adapter 需要完成各自的角色／參數／finish reason／usage 轉換、真正網路政策與 timeout、Credential 注入、錯誤轉換及離線測試。Ollama／Custom endpoint 的本機網路需求應另行設計與審查，不可自動豁免地址限制。

未來的 `ai.generate`、`ai.summarize`、`ai.classify`、`ai.extract` 只屬設計方向：AI Node Executor 從合法的啟動上游取得資料 → 建立 AIRequest → 呼叫可信 AI Service／Registry → 將 AIResponse 轉成 JSON output。Provider 不讀 Context 內部結構、不訪問 Workflow DB 或 Scheduler。Readiness 仍應離線，輸出仍受 Engine 的深度與累計大小限制；不改 Condition 或依賴語意。

## Security

- Key 未來只能由可信後端配置來源注入 Adapter，不放 Workflow JSON、Context、Registry Metadata、公開配置、前端或日誌；目前不要求 OPENAI／ANTHROPIC／GEMINI Key，也沒有 Secret Manager。
- Prompt／Response 不自動寫日誌或永久保存；request messages／response content／metadata 不出現在一般 model repr。
- 常見 Metadata 憑證 key 檢查不是秘密掃描，任意文字可能仍含敏感內容。呼叫端仍須避免將秘密送入資料，不能宣稱 Schema 能辨識所有 Key。
- 模型輸出屬不可信資料，不能直接執行 Python／Shell、修改 Workflow、控制 Scheduler 或取得任意系統權限。
- Mock 不在 Node Registry 註冊，也沒有無認證公開 AI API。Flag 為 true 不會使其變成真正 AI。
- Protocol／Metadata 檢查不是任意 Python 程式碼的安全沙盒；Registry 只能接收可信開發者建立的 Adapter。
- 架構完成與發布準備分開：Docker／遠端 CI 等未驗證項目仍見 [Phase 07B Readiness](PHASE_07B_RELEASE_READINESS.md)。
