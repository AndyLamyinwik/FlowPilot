# FlowPilot v0.1.0 Release Checklist

Verification date: 2026-10-29 (Asia/Shanghai). Candidate: **0.1.0, unreleased Early Public Release**.

Phase 09 recheck: **2026-10-30 (Asia/Shanghai), RELEASE_PARTIALLY_COMPLETED / formal-release NOT_READY**. Backend 796, frontend 274 and production server 12 tests passed again, along with typecheck, build, both Compose configurations and actionlint. The Public [FlowPilot repository](https://github.com/AndyLamyinwik/FlowPilot) and private-reporting entry are verified. The user's later explicit instruction authorizes publishing the complete reviewed source now, so source commit/push is separate from formal tag/Release acceptance. Exact-commit remote CI and Docker runtime results must still be established, without misreporting local parsing as runtime acceptance. See the [Phase 09 report](PHASE_09_RELEASE_REPORT.md). Detailed test/dependency tables retain dated Phase 08B evidence unless a newer result is stated.

## Release Decision

**NOT_READY for a formal v0.1.0 tag/Release.** Complete reviewed source is published under the user's additional authorization. Initial 194-file staged-source review passed; a separate formatting check reports existing CRLF/EOF notices. Critical Docker runtime and exact-commit CI evidence remain outstanding. No tag, GitHub Release or image publication is claimed.

Statuses are literal: **PASS**, **FAIL**, **NOT_TESTED**, **NOT_APPLICABLE**, **BLOCKED**. A local passing check does not turn a remote or container check into PASS. No new unresolved P0/P1 was confirmed in this scoped preparation; the existing three P2 issues remain disclosed.

## Release Blockers

| ID | Status | Required maintainer action |
| --- | --- | --- |
| R1 — Docker runtime acceptance | NOT_TESTED | On a Docker Engine host, build and start an isolated project; verify health, browser/API connectivity, stop/start, container recreation, SQLite permissions/persistence and scheduler recovery. Current environment: **DOCKER_NOT_TESTED / DOCKER_UNAVAILABLE**. |
| R2 — Repository identity and initial candidate review | PASS | Public target, owner/default main and empty remote refs verified. All 194 staged blobs equal reviewed files; bounded secret/artifact/visual checks and 24 ignore probes passed. No prior local commits/remote refs; recheck subsequent changes and refs/protection before commit/push. |
| R3 — Private vulnerability reporting configuration | PASS | Enabled after explicit consent; setting and public Report a vulnerability entry verified. SECURITY contains the real route. No report/advisory was submitted and notification delivery was not tested. |
| R4 — Remote GitHub Actions | NOT_TESTED | Run the existing workflow against the reviewed source in the intended repository and inspect all jobs. No remote workflow run is available here; publication is not authorized by this checklist. |

## Code

| Check | Status | Evidence |
| --- | --- | --- |
| Core APIs, Engine, branches, Scheduler, persistence and AI Mock regression | PASS | Complete backend suite: **796 passed in 53.42s**; includes the existing 788 tests and 8 release-example tests. |
| Backend API and execution behavior | PASS | CRUD, general validation versus strict readiness, HTTP 200 failed, skipped branches and history covered by existing and new tests. |
| Frontend unit/component tests | PASS | **274 passed**, 19 files, 53.01s. |
| Production frontend server tests | PASS | **12 passed**, 0 skipped. |
| TypeScript check | PASS | npm run typecheck. |
| Production frontend build | PASS | npm run build; 197 modules, no blocking error. |
| AI Provider tests | PASS | Included in full backend run; Mock only, no real model request, SDK, key or model download. |
| Product scope unchanged | PASS | Existing app/frontend source, dependency files and runtime configuration hashes unchanged. Only release documents/examples/tests and backend context exclusions were added or updated. |
| Existing P2 resolution | FAIL | FP07A-002: large-integer config can block workflow lists; 003: deleted-node stale result selection; 004: extreme history offset returns controlled 500. These remain known limitations, not hidden passing claims. See the [audit](PHASE_07A_AUDIT.md). |

## Docker

| Check | Status | Evidence |
| --- | --- | --- |
| Default Compose config | PASS | Official standalone Compose 5.6.0 config --quiet. |
| .env.example Compose config | PASS | Same validation with --env-file .env.example. |
| Dockerfile/context review | PASS | Existing pinned runtimes, hashed backend install, npm ci/multistage frontend, no dev server in runtime; context exclusions retained and backend exclusions strengthened. |
| Docker build | NOT_TESTED | No docker executable/Engine pipe; no image build claimed. |
| Docker startup and container health | NOT_TESTED | Native Uvicorn/Node evidence is separate from container execution. |
| Container stop/start/recreation and data persistence | NOT_TESTED | Requires R1. No production database or volume was deleted. |
| Native production frontend/backend and sample history | PASS | Isolated Uvicorn and dist/Node runtime; imported three exact release payloads, executed Manual Logger, checked matching successful history, and left the schedule disabled. |
| Prior native process restart/Scheduler recovery | PASS | Previously executed and retained as Phase 07B evidence; not rerun or represented as Docker verification in this phase. See [readiness report](PHASE_07B_RELEASE_READINESS.md). |

## Documentation

| Check | Status | Evidence |
| --- | --- | --- |
| README | PASS | Primarily English; actual features, local-first limits, configuration, first workflow, scheduling, troubleshooting and document links. |
| LICENSE | PASS | Existing standard MIT text and `Copyright (c) 2026 FlowPilot contributors` preserved byte-for-byte. No holder or conditions invented. |
| CONTRIBUTING | PASS | Locked dependency setup, project structure, tests, compatibility expectations and PR/report guidance. |
| SECURITY document | PASS | Local/trusted deployment, inbound versus outbound policy, secrets, data and AI boundaries documented. |
| Operational private reporting setting/entry | PASS | Phase 09: explicitly authorized, enabled and public entry verified. No report submitted or notification delivery tested. |
| CHANGELOG | PASS | Unreleased preparation and 0.1.0 unreleased candidate are distinct; no fictional older release or release date. |
| Quick Start/configuration consistency | PASS | Source/config cross-check completed; actual Docker Quick Start remains NOT_TESTED. The verified repository URL points to complete source; formal release limits remain explicit. |
| Release Notes | PASS | [v0.1.0 draft](releases/v0.1.0.md), English, unreleased, limits disclosed. |
| Workflow examples | PASS | Three validated payloads and an [API import/setup guide](../examples/workflows/README.md); no file-import UI is claimed. |
| Screenshots | PASS | Three genuine 1280×720 JPEGs from an isolated running current app, visually inspected; no keys, private workflow data or local filesystem paths. No synthetic UI. |
| Links/fences/version references | PASS | 13 Markdown files, 80 relative links and 182 candidate text files checked; no broken links, unclosed fences or UTF-8 errors. Application version references agree at 0.1.0. |

## Examples

| Example | Status | Meaning |
| --- | --- | --- |
| manual-logger.json | PASS | Manual → Logger → Logger executes offline; Node/Execution IDs and default-private history verified. |
| scheduled-logger.json | PASS | UTC */5 Cron; API creation leaves enabled=false, next_run_at=null and no workflow Job. Requires explicit enable. No enabled field is invented inside Definition. |
| api-condition.json | PASS | Version 1 structure/DAG and true/false handles verified; controlled Mock Transport/resolver tests execute each selected branch and skip the other. |
| HTTP example on a real external service | NOT_TESTED | Intentionally not sent. Default empty allowlist produces readiness 422; real use requires explicit destination setup without weakening other HTTP controls. |

Eight focused example tests cover JSON/Pydantic parsing, save/read/general validation, manual execution/history, disabled schedule admission, default HTTP denial and both controlled branches. Structural validity is not a promise of executor readiness or external service availability.

## Security and Repository Hygiene

| Check | Status | Evidence/limit |
| --- | --- | --- |
| Current candidate source secret-pattern scan | PASS | Bounded scan of 182 candidate text files found no high-confidence private-key/provider-token patterns or unexpected sensitive source paths. Scan outputs only path/type/line, never matched values; this is not complete secret detection. |
| Initial staged-source/history exposure review | PASS | Phase 09: 194 explicit staged paths match reviewed bytes; no prior local commits or remote refs. Bounded review passed; recheck changes and refs before eventual publication. |
| Ignore rules and retained local artifacts | PASS | .env, environments, node_modules, DB/journals, logs, caches/builds and keys excluded. Local artifacts were retained, not deleted. Never upload the entire unfiltered working directory as a release archive. |
| Backend Docker context | PASS | Added key/credential, journal/instance-lock and local-tool exclusions; existing build-required app/requirements remain included. |
| Local-first exposure | PASS | Compose only publishes 127.0.0.1:5173/8000, one backend worker/replica; exact Host policy remains. No authentication/public-service safety claim. |
| Outbound HTTP restrictions | PASS | Empty default allowlist, HTTPS/public-address/DNS/pinned-target/redirect/proxy/time/size controls unchanged; tests use controlled HTTP substitutes. |
| No arbitrary execution | PASS | No release-phase changes to executors; config/model output does not gain Python, Shell, DB or scheduler authority. |
| Sensitive output handling | PASS | Existing default no-output history and bounded basic redaction retained; arbitrary text secrets cannot be fully classified. |
| Production user data | PASS | data/flowpilot.db remains 0 bytes; original SHA-256 unchanged. All new executions used isolated data. |
| Full history secret scan, container CVE audit, full transitive legal/security review | NOT_TESTED | No such guarantee is made. |

### Direct Dependency License Review

Locally inspected the declared license metadata of **23 direct runtime/development packages**, using installed Python distribution metadata and npm package.json/license files. No obvious conflicting declaration was identified:

| Declaration | Packages |
| --- | --- |
| MIT | APScheduler, FastAPI, Pydantic, pydantic-settings, Pytest; React, React DOM, React Flow; remaining directly declared npm tools except TypeScript |
| BSD-3-Clause | httpx2, Uvicorn |
| Apache-2.0 | tzdata, TypeScript |

This is a bounded declaration check, not a legal opinion, proof of all asset provenance or a full transitive/container-license audit. Third-party licenses remain applicable; the project's MIT license does not relicense dependencies. Preserve applicable notices when preparing distributed bundles/images. The original project LICENSE was not modified.

## GitHub and Versioning

| Check | Status | Evidence |
| --- | --- | --- |
| Single CI configuration | PASS | Existing .github/workflows/ci.yml retained; backend/frontend/Docker config/build jobs, no duplicate or publishing workflow. |
| Local workflow validation | PASS | actionlint 1.7.12; ShellCheck/Pyflakes unavailable and not claimed. |
| CI permissions and pinned Actions | PASS | contents:read, no persisted checkout credentials, no PR-text shell interpolation or real secrets; exact SHAs match retained official verification evidence. |
| Remote CI | NOT_TESTED | R4. Local commands do not prove GitHub execution. |
| Description/topics/about suggestions prepared | PASS | See below; no remote settings changed. |
| Repository creation/description | PASS | Phase 09: verified Public repository, exact name and documented description created after explicit consent. No official website invented; topics remain suggestions. |
| Candidate application versions | PASS | backend pyproject, FastAPI app, frontend package.json and root package-lock entry all 0.1.0. Backend remains an application, not a newly published Python package; frontend stays private for npm publication. |
| Published Docker image version | NOT_APPLICABLE | No application image published or image tag created; base image runtime versions are not the application version. |
| Git tag/GitHub Release | NOT_TESTED | Source commit/push is separately authorized now; formal tag/Release still requires passing gates and exact-commit CI. Image publication remains outside scope. |

Retained official verification links for existing immutable Action pins: [checkout](https://github.com/actions/checkout/commit/d23441a48e516b6c34aea4fa41551a30e30af803), [setup-python](https://github.com/actions/setup-python/commit/ece7cb06caefa5fff74198d8649806c4678c61a1), [setup-node](https://github.com/actions/setup-node/commit/249970729cb0ef3589644e2896645e5dc5ba9c38). No SHA was guessed or changed in this phase.

**Suggested description:** Lightweight, self-hosted workflow automation platform with a visual editor and AI-ready architecture.

**Suggested topics:** workflow-automation, automation, self-hosted, react, fastapi, python, typescript, docker, workflow-engine, react-flow, open-source.

**About:** Build and run visual automation workflows on your own machine. AI is optional; this candidate includes provider contracts and an offline Mock only. Leave the homepage unset until a real URL is verified. These are suggestions, not applied settings.

**Version policy:** 0.1.x is early development; APIs and workflow formats may change with documented compatibility/migration notes. Consider 1.0.0 only after stable public interfaces are established. No date or long-term compatibility commitment is made. The versioned Workflow Definition schema remains 1.

## Actual Verification Commands

```powershell
# backend/
.\.venv\Scripts\python.exe -m pytest tests/test_release_examples.py -q --tb=short --basetemp=.pytest_cache/phase08b-examples
.\.venv\Scripts\python.exe -m pytest -q --tb=short --basetemp=.pytest_cache/phase08b-regression

# frontend/ (local npm CLI used because no global npm is available)
node .tools/npm11/package/bin/npm-cli.js test
node .tools/npm11/package/bin/npm-cli.js run test:server
node .tools/npm11/package/bin/npm-cli.js run typecheck
node .tools/npm11/package/bin/npm-cli.js run build

# root
.\.tools\compose\docker-compose.exe config --quiet
.\.tools\compose\docker-compose.exe --env-file .env.example config --quiet
.\.tools\phase07b-ci\actionlint-1.7.12\actionlint.exe -shellcheck= -pyflakes= .github/workflows/ci.yml
```

The screenshot instance reused the existing production smoke harness in a new .tools/phase08b-* directory, with a new SQLite file and loopback-only Uvicorn/Node. Three example payloads were created through the real API; only the offline manual workflow was executed. Dashboard/editor/history screenshots reflect its actual successful record. A browser tool connection interruption was recovered before the History capture; no synthetic substitute was used. Temporary services were stopped and the test tab closed.

Final local checks also verify document links/fences, JPEG files, example/schema agreement, exact version values, 117 protected source/license/dependency/data hashes and source inventory patterns. All 117 protected hashes are unchanged. Ignored evidence stays in .tools/phase08b-*; it is not a release artifact.

## Maintainer Review

Complete Docker acceptance (R1), recheck the reviewed candidate and target, then require exact-commit remote CI (R4) before any tag/Release. Triage/accept or fix the three P2 limitations and preserve third-party notices. R2 initial review and R3 setting/entry now pass within their stated limits. Change this decision only with actual evidence; conditional Phase 09 authorization does not waive the remaining gates.
