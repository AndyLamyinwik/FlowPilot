# FlowPilot v0.1.0 — Final Release Report

Verification date: **2026-10-30 (Asia/Shanghai)**. This is the acceptance record frozen before tag creation. Actual final commit, tag, Release URL and publication result must be verified after publication and recorded in the execution summary or a subsequent documentation commit; the released tag must never be moved to add that report.

## Release Status

**RELEASE_PARTIALLY_COMPLETED at this pre-publication freeze. Acceptance: READY_WITH_WARNINGS for final commit/push and exact-commit CI.** Source is public, local regression and remote container acceptance pass, and the user explicitly approved the narrow FP07A-002 frontend exception. The fix now passes regression and real production frontend/backend browser verification. No unresolved P0 or release-blocking P1 is known from the scoped audit. The remaining localized P2 limitations below do not block supported editing/execution/history flows or identify a security/storage-integrity issue. Tag/Release remains prohibited until the final commit's own necessary CI succeeds and its target is verified. No image publication or v0.2.0 work is authorized.

## Release Identity

| Field | Verified state at freeze |
| --- | --- |
| Version | 0.1.0, Early Public Release preparation |
| Repository | [AndyLamyinwik/FlowPilot](https://github.com/AndyLamyinwik/FlowPilot), ID 1438711382, Public |
| Branch | main; complete reviewed source, tests, examples, configuration and documentation |
| Accepted runtime commit | [7fad8be8c7cf368c3a2dc418856d13f61c565a75](https://github.com/AndyLamyinwik/FlowPilot/commit/7fad8be8c7cf368c3a2dc418856d13f61c565a75) |
| Accepted CI | [Run 40922436437](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/40922436437), all three jobs and all required steps successful |
| Final release commit | The final documentation commit must independently pass the same CI; the execution summary records its exact SHA |
| Tag / Release | v0.1.0 / FlowPilot v0.1.0 — Initial Public Release; not yet created at this freeze |
| Release date / URL | Record the actual publication result after creation; this verification date is not proof of publication |

## Source Upload and Acceptance History

- Initial complete source was normally pushed as **8847cf3605cc2a3dbcf3d6c892b6b5960609d232**, 194 files. Its [CI](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/40920568507) passed backend, frontend and both Docker builds.
- Commit **679d2f4b3a1a18e9582b52f1c8e94b2b23b6f285** added the isolated Docker verification script and one step to the existing read-only CI. Its [attempt](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/40921193492) passed startup, API, execution/history and schedule enablement, then failed because Compose start does not support --wait. That failed attempt is retained, not relabeled as successful.
- Commit **7fad8be8c7cf368c3a2dc418856d13f61c565a75** removed only that unsupported flag, retaining health/persistence assertions. Its [CI](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/40922436437) passed **Backend tests**, **Frontend checks**, and **Docker build and acceptance**, including the complete runtime step. The Docker log explicitly reports PASS for startup, proxy/API, execution/history, persistent data, restart and schedule recovery.
- The public tree contains **197 tracked files**, including English, Traditional Chinese and Simplified Chinese introductions. GitHub About was updated with the same three languages at the user's request. A public isolated clone of 679d2f4 matched all 195 files at that commit and passed locked offline npm ci, typecheck and production build with unchanged lockfile and clean tracked working tree. Later public additions were Chinese documentation and the smoke-test compatibility correction. The final release commit also includes the separately approved FP07A-002 fix described below.

## Tests and Deployment Evidence

| Check | Status | Actual evidence / scope |
| --- | --- | --- |
| Local complete backend suite | PASS | **796 passed in 10.50s**, including Engine, Executors, API, Scheduler, History, AI Mock and release examples |
| Local frontend unit/component suite | PASS | **282 passed**, 19 files, after the approved fix (274 existing plus 8 regressions) |
| Local production frontend server | PASS | **12 passed**, 0 skipped |
| Local TypeScript / production build | PASS | Rerun after the approved fix: tsc --noEmit and 197 modules built |
| Approved list-isolation regression | PASS | Original baseline fails the new mixed-list test; corrected code passes all 282 tests. Unsafe config is absent from summaries and direct editor load remains rejected |
| Actual production browser / API integration | PASS | Dashboard and Open show both normal/unsafe workflows; normal editor opens; unsafe load leaves current canvas unchanged; subsequent UI run succeeds for all 3 nodes. Backend retains exact integers 9007199254740993 and 10**400 before/after |
| Compose default / example environment | PASS | Both standalone Compose 5.6.0 config checks |
| Workflow syntax | PASS | actionlint 1.7.12; ShellCheck/Pyflakes were not run locally |
| Remote locked installations and regression | PASS | Exact 7fad8be run: backend and frontend jobs, including dependency/syntax, typecheck, tests and build |
| Remote Docker image builds | PASS | Both production images built on GitHub Ubuntu 24.04 |
| Remote startup / frontend / API | PASS | Fresh isolated Compose project; backend and frontend proxy health plus production HTML |
| Remote execution / history | PASS | Real manual example imported, validated and successfully executed; matching history and default no-output persistence |
| Remote SQLite write / persistence / permissions | PASS | Fresh runner-only bind directory; workflow, history and schedule metadata survive backend stop/start and forced container recreation |
| Remote scheduler recovery | PASS | Explicitly enabled future UTC schedule survives both restarts, scheduler remains enabled, no historical execution is replayed; schedule disabled before cleanup |
| Local Docker runtime | NOT_TESTED | Docker CLI/Engine unavailable on the Windows workstation; remote Linux acceptance does not certify this local host or every platform |
| Initial staged-source review | PASS | 194 explicit files, 183 text files, 8 visually inspected JPEGs, 3 placeholders and 24 ignore probes; no unresolved suspected real credential |
| Initial-import whitespace check | FAIL (format only) | Existing CRLF/EOF formatting produced 482 notices in 16 files. Product tests passed; protected source/LICENSE/dependency bytes were preserved. Later targeted changes pass diff --check |
| Private vulnerability reporting | PASS | Explicitly approved, enabled setting and public reporting entry verified |
| Report submission / notification delivery | NOT_TESTED | No fake vulnerability/advisory was submitted |

The first local production-server test attempt encountered sandbox loopback EACCES. The retained failure was followed by an approved local-socket execution passing all 12 tests; no weaker security setting or source modification was used.

The Docker smoke script uses a unique CI project and temporary data directory. It checks loopback bindings and the isolated mount before startup, verifies fresh and recovered state, and cleans up only its own project without down -v. The user's data/flowpilot.db remains the original 0-byte file. A passing remote container test does not imply distributed, exactly-once or public-service guarantees.

## Gate Assessment

| Gate | Status | Evidence / remaining condition |
| --- | --- | --- |
| R1 — Docker deployment | PASS | Real image builds, startup, proxy/API, stop/start, recreation, persistent data and scheduler recovery in exact 7fad8be CI |
| R2 — Repository/source identity | PASS | Verified owner, Public target and main; normal pushes succeeded; bounded reviewed source/history/artifact checks found no unresolved suspected real secret; no force push or history rewrite |
| R3 — Private reporting route | PASS | Enabled after explicit user consent; anonymous public advisory page links to the real private reporting route; SECURITY agrees |
| R4 — Necessary remote CI | PASS for 7fad8be | Every necessary job passed for that exact SHA. A final documentation commit must pass its own CI before tagging; old success cannot certify it |
| P0 / P1 | PASS within scoped review | No unresolved P0 or release-blocking P1 identified; previously fixed history identity and Host-boundary issues remain covered |
| Core warning assessment | PASS with disclosed P2 | FP07A-002 fixed under explicit user authorization and verified with baseline RED, full regression and real browser/API integration. Remaining FP07A-003/004 are localized stale-result / unsupported extreme-pagination cases with independent working paths |
| Version / license / AI accuracy | PASS | Backend/FastAPI/frontend/lockfile agree at 0.1.0; schema remains 1; original MIT LICENSE retained; offline Mock only |

### Approved FP07A-002 Correction

The user explicitly approved the six-file frontend proposal after reviewing its scope, overriding only the existing no-frontend rule for this bug. listWorkflows now returns a typed read-only WorkflowSummary. Existing metadata, position, graph, edge/handle and config-object-shape checks stay in place. The summary path does not interpret configuration values and immediately discards config/positions; full workflow paths retain all strict finite-JSON and safe-integer validation. Full get/create/update responses and editor serialization retain strict precision protection. Unknown normal config and edge handles remain intact on the normal full-workflow path. The Dashboard and Open consumer changes are type-only; there is no backend API/schema, Engine, Scheduler or dependency change.

The new mixed-list test reproduces the original failure on the baseline. The actual corrected suite passes 282 tests, typecheck and production build. Real Uvicorn plus the rebuilt dist/Node frontend use fresh isolated SQLite: normal and both unsafe-integer list entries render, a normal workflow opens, an unsafe load is refused without replacing the current graph, the normal workflow then executes successfully through the UI, and exact backend integers remain unchanged. Test services were stopped; the original user database hash is unchanged.

### Remaining Non-blocking Limitations

- **FP07A-003:** After a node is deleted, a retained in-memory execution panel can show the previously selected node. This affects selection of a stale result after the graph changes; original results remain available through independent History Detail or by clearing canvas selection. Stored history and execution are unaffected.
- **FP07A-004:** A manually supplied history offset beyond SQLite int64 returns a controlled generic 500 instead of 422. Ordinary UI pagination and subsequent health work; no stack/secret exposure was observed.

See the [original audit](PHASE_07A_AUDIT.md). These localized edge cases do not block the verified supported core flows, storage integrity or publication completeness. No additional maintainer permission is pending. They remain candidates for separately authorized future work; they are not marked fixed.

## Security, Scope and Repository Verification

The authenticated connector and browser confirmed AndyLamyinwik, the exact repository, Public visibility and administrative/push metadata; actual normal source pushes confirm write capability. gh is unavailable, so no fictional gh auth success is reported. A separate collaborator-permission endpoint returned integration-scope 403; that result is preserved as a limitation. Release creation and tag permissions must be established by their actual successful operations.

Repository creation with the ChatGPTBot auto-connection and Private Vulnerability Reporting were each separately approved by the user after initial review rejections. Those precise settings were applied and verified; no other scanning, AI/autofix, account permission or visibility change was made. The public [advisory page](https://github.com/AndyLamyinwik/FlowPilot/security/advisories) exposes the private route documented in SECURITY; owner/reporter UI differences follow [GitHub's instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

Bounded source/path/pattern and screenshot review found no unresolved suspected real credentials or unexpected sensitive tracked artifacts. Credential-like test values were reviewed with masked values as validation/redaction fixtures. The finite review is not proof of complete secret detection, a container CVE scan or a full legal/transitive dependency audit. The initial Git history contained no prior commits; subsequent commits contain reviewed release/CI/documentation changes only. Local .env, SQLite/journals, environments, dependencies, builds, logs, caches, tools and keys remain excluded.

Of the **117 protected baseline files**, **110 remain byte-identical**. The seven reviewed exceptions are the existing CI file extended for isolated deployment verification and the six explicitly approved frontend correction/test files. Original LICENSE, dependencies/locks, Compose, backend Engine/Scheduler/API/Schema and the 0-byte user database are unchanged. The added Docker script contains test orchestration only; no new product capability is introduced. Direct dependency license declarations reviewed in Phase 08B are preserved; no dependency upgrades were made.

Default ports remain loopback-only. Exact inbound Host checks and the separate empty outbound allowlist, HTTPS, DNS/address validation and pinned target, disabled redirects/environment proxy, time and size limits remain in place. No complete SSRF guarantee is made. History output storage defaults to false; optional basic redaction cannot recognize every secret. There is no built-in authentication: **do not expose the unauthenticated service directly to the public Internet**.

AI consists of provider contracts, a registry and one offline Mock. There are no real OpenAI/Claude/Gemini/Ollama integrations, AI executors, SDKs, model downloads or public AI endpoints. No prompt/model-generated action gains shell, filesystem, database or scheduler authority.

## Publication Sequence and Recovery

After the final reviewed documentation commit is normally pushed, inspect its own completed CI. Only then, recheck that v0.1.0 does not already exist, create an annotated tag pointing to that exact successful commit, push the single tag normally and verify its remote peeled commit. Create the GitHub Release with the reviewed [release notes](releases/v0.1.0.md), then verify the public Release, tag, source, README/LICENSE/examples and links. If any operation fails, preserve successful steps and report the actual partial state; never overwrite a tag or bypass CI/protection.

The final operation summary must record the actual release commit SHA, CI URL, tag target, Release URL and publication date. A subsequent documentation-only maintenance commit may record publication without moving the released tag. Ignored evidence remains in .tools/phase09 and is not a release asset. Stop after Phase 09; no Docker Hub image or v0.2.0 development.
