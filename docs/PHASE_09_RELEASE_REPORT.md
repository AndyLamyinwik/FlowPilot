# FlowPilot v0.1.0 — Final Release Report

Publication and verification date: **2026-10-30 (Asia/Shanghai)**.

## Release Status

**RELEASE_SUCCESSFUL.** FlowPilot v0.1.0 is published as an Early Public Release with disclosed non-blocking limitations. The complete source, annotated tag and GitHub Release are publicly accessible. All necessary branch and tag CI jobs passed for the exact released commit before publication, including actual Docker runtime acceptance. FP07A-002 was fixed under the user's narrow authorization and verified locally, through the real production frontend/backend, and in exact-commit remote CI. No unresolved P0 or release-blocking P1 was identified in the scoped review.

This post-publication documentation update records actual operations. It does not move the published tag or change the release source. No image publication or v0.2.0 work was performed.

## Release Identity

| Field | Verified published state |
| --- | --- |
| Version | v0.1.0 — Early Public Release |
| Repository | [AndyLamyinwik/FlowPilot](https://github.com/AndyLamyinwik/FlowPilot), ID 1438711382, Public, default main |
| Release | [FlowPilot v0.1.0 — Initial Public Release](https://github.com/AndyLamyinwik/FlowPilot/releases/tag/v0.1.0), ID 428647837, published, not draft |
| Released commit | [036bb95754064f1d12cbc6d386afc51615b7983a](https://github.com/AndyLamyinwik/FlowPilot/commit/036bb95754064f1d12cbc6d386afc51615b7983a) |
| Annotated tag | v0.1.0; tag object 2047fd5d111c960afeb01e1273ee13fdcac0d610; remote peeled commit equals the released commit |
| Publication time | 2026-10-30 12:16:18 Asia/Shanghai (04:16:18 UTC) |
| Exact commit branch CI | [Run 41001272625](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/41001272625), all three jobs / necessary steps successful before tag creation |
| Exact commit tag CI | [Run 41001570054](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/41001570054), all three jobs / necessary steps successful before Release publication |
| Release body | Matches the reviewed version notes with final CI, tagged clone instructions and three language links |
| Source downloads | Generated ZIP downloaded with HTTP 200 and all 197 archive paths match the exact tag tree; MIT LICENSE and fix bytes verified. Tar endpoint present, not downloaded; no custom binary or Docker Hub image uploaded |
| Final report handling | Subsequent documentation-only maintenance commit; published tag remains fixed at 036bb95754064f1d12cbc6d386afc51615b7983a |

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
| Remote locked installations and regression | PASS | Exact released 036bb95: 796 backend, 282 frontend and 12 production-server tests; dependency/syntax, typecheck and production build all pass |
| Remote Docker image builds | PASS | Both production images built for exact 036bb95 on GitHub Ubuntu 24.04, in branch and tag runs |
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
| R1 — Docker deployment | PASS | Real image builds, startup, proxy/API, stop/start, recreation, persistent data and scheduler recovery in exact released 036bb95 CI |
| R2 — Repository/source identity | PASS | Verified owner, Public target and main; normal pushes succeeded; bounded reviewed source/history/artifact checks found no unresolved suspected real secret; no force push or history rewrite |
| R3 — Private reporting route | PASS | Enabled after explicit user consent; anonymous public advisory page links to the real private reporting route; SECURITY agrees |
| R4 — Necessary remote CI | PASS | Both branch run 41001272625 and tag run 41001570054 passed for released 036bb95 before publication; no old run used to certify it |
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

The authenticated connector and browser confirmed AndyLamyinwik, the exact repository, Public visibility and administrative/push metadata; actual normal source pushes confirm write capability. gh is unavailable, so no fictional gh auth success is reported. A separate collaborator-permission endpoint returned integration-scope 403; that result is preserved as a limitation. Successful annotated tag push and GitHub Release creation now establish those actual write operations; no CLI authentication result was invented.

Repository creation with the ChatGPTBot auto-connection and Private Vulnerability Reporting were each separately approved by the user after initial review rejections. Those precise settings were applied and verified; no other scanning, AI/autofix, account permission or visibility change was made. The public [advisory page](https://github.com/AndyLamyinwik/FlowPilot/security/advisories) exposes the private route documented in SECURITY; owner/reporter UI differences follow [GitHub's instructions](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

Bounded source/path/pattern and screenshot review found no unresolved suspected real credentials or unexpected sensitive tracked artifacts. Credential-like test values were reviewed with masked values as validation/redaction fixtures. The finite review is not proof of complete secret detection, a container CVE scan or a full legal/transitive dependency audit. The initial Git history contained no prior commits; subsequent commits contain reviewed release/CI/documentation changes only. Local .env, SQLite/journals, environments, dependencies, builds, logs, caches, tools and keys remain excluded.

Of the **117 protected baseline files**, **110 remain byte-identical**. The seven reviewed exceptions are the existing CI file extended for isolated deployment verification and the six explicitly approved frontend correction/test files. Original LICENSE, dependencies/locks, Compose, backend Engine/Scheduler/API/Schema and the 0-byte user database are unchanged. The added Docker script contains test orchestration only; no new product capability is introduced. Direct dependency license declarations reviewed in Phase 08B are preserved; no dependency upgrades were made.

Default ports remain loopback-only. Exact inbound Host checks and the separate empty outbound allowlist, HTTPS, DNS/address validation and pinned target, disabled redirects/environment proxy, time and size limits remain in place. No complete SSRF guarantee is made. History output storage defaults to false; optional basic redaction cannot recognize every secret. There is no built-in authentication: **do not expose the unauthenticated service directly to the public Internet**.

AI consists of provider contracts, a registry and one offline Mock. There are no real OpenAI/Claude/Gemini/Ollama integrations, AI executors, SDKs, model downloads or public AI endpoints. No prompt/model-generated action gains shell, filesystem, database or scheduler authority.

## Publication and Post-release Verification

The final reviewed release commit was normally pushed to main as 036bb95754064f1d12cbc6d386afc51615b7983a. All necessary jobs for that exact SHA passed. Local and remote v0.1.0 absence was checked, an annotated tag was created and normally pushed, and its remote peeled target was confirmed. The tag-triggered run also passed all necessary jobs before the existing tag was selected on GitHub's authenticated release form and the reviewed title/body published.

The live Release page and public API agree on the actual Release URL, title, tag, published state and commit. The published body matches the reviewed notes. Repository metadata confirms Public visibility and main. Twelve tag-specific connector checks verified README in three languages, original MIT LICENSE, documentation targets and all three workflow examples. All 16 Markdown files passed UTF-8/fence and 127 relative-link checks before the final release commit; the post-publication documentation check passes 125 relative links; external versioned documentation targets were then verified after tag creation. The public source tree contains 197 tracked files, excluding private runtime/build artifacts.

A fresh independent public clone of the exact released commit matched its complete Git tree, installed 131 packages from the existing lockfile and passed production build including TypeScript (197 modules). The first offline install failed because the selected cache lacked an artifact; a normal locked install from the official npm registry passed. An initial raw-byte comparison between clone and workspace lockfiles differed solely due Windows autocrlf checkout; LF-normalized bytes, parsed lock content and clean tracked clone state confirmed no dependency/lock change. These failed preliminary checks are not mislabeled successful offline or byte-identical checks.

The report/status/checklist are updated in a normal documentation-only maintenance commit after publication, as allowed by Phase 09. The released tag continues to identify 036bb95754064f1d12cbc6d386afc51615b7983a; it is never rewritten to add this report. Ignored local evidence and screenshots remain in .tools/phase09 and are not release assets. Phase 09 is complete. Stop here; no Docker Hub image or v0.2.0 development.
