# Changelog

Changes are grouped by version. Final acceptance and publication status are recorded in the [release checklist](docs/RELEASE_CHECKLIST.md).

## [Unreleased]

### Documentation

- Record the published v0.1.0 Release, exact release commit, and passing branch/tag CI in the English, Traditional Chinese, and Simplified Chinese introductions and acceptance documents. Product code and the existing release tag are unchanged.

## [0.1.0] — 2026-10-30

**[Initial Public Release](https://github.com/AndyLamyinwik/FlowPilot/releases/tag/v0.1.0)**, local-first and self-hosted. Both [branch CI](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/41001272625) and [tag CI](https://github.com/AndyLamyinwik/FlowPilot/actions/runs/41001570054) passed for the exact release commit `036bb95754064f1d12cbc6d386afc51615b7983a`: 796 backend tests, 282 frontend tests, 12 production server tests, TypeScript, production build, and real Docker acceptance.

### Release Preparation

- Traditional Chinese and Simplified Chinese introductions, README language navigation, and a trilingual GitHub About description.
- Isolated Docker startup, execution/history and persistence/recreation acceptance in the existing CI; a Compose start-flag compatibility issue found by the first runtime attempt was corrected without weakening health checks.
- English project overview, installation guidance, and explicit deployment limits.
- Contribution and security policies, including instructions for GitHub Private Vulnerability Reporting.
- Release notes, a release checklist, and workflow examples for the first public test version.
- Repository safety, version consistency, CI, and regression verification recorded without treating unperformed checks as passed.
- Complete reviewed source, tests, examples and documentation published to the Public FlowPilot repository, followed by the annotated v0.1.0 tag and GitHub Release after final acceptance.
- Private vulnerability reporting enabled. The saved setting and public reporting entry were verified on 2026-10-30; no test report/advisory was submitted or notification delivery tested.

### Added

- Workflow Dashboard and React Flow visual editor with node placement, connections, properties, draft preservation, and Explicit Save.
- Workflow CRUD, structural validation, versioned JSON definitions, and SQLite persistence.
- Deterministic DAG execution with execution-local context, conditional branch activation, joins, skipped nodes, and fail-fast behavior.
- Seven implemented node types: Manual Trigger, Schedule Trigger, HTTP Request, Condition, Transform, Outgoing Webhook, and Logger.
- Single-instance Cron scheduling, enable/disable controls, timezone configuration, and backend-reported next-run times.
- Execution results, node status displays, paginated history, details, and interrupted-record recovery without automatic replay.
- Docker Compose definitions for two loopback-bound services, persistent SQLite data, and application health checks. Linux CI verified image builds, startup, API proxy connectivity, execution/history, and persistence/schedule recovery after restart and recreation.
- A single GitHub Actions workflow for backend tests, frontend checks, Docker configuration/image builds, and isolated runtime acceptance, with read-only permissions and pinned Action commits.
- Independent text AI request/response contracts, synchronous provider interface, explicit registry, safe errors, and an offline Mock Provider. No real AI integration is included.

### Changed

- The frontend container uses a production build and a small Node static/API proxy server instead of the Vite development server.
- Browser API configuration uses a public build-time base URL; the production proxy target remains server-only runtime configuration.

### Fixed

- History retains complete node IDs and error references when stored, preventing distinct long IDs from becoming the same truncated prefix. Oversized history omits complete summaries or nullable references rather than slicing identity values.
- FP07A-002: workflow lists validate and project summary metadata separately from editable definitions. One definition containing a browser-unsafe integer no longer blocks other workflows from being listed or opened. Strict precision checks still prevent editing or saving that unsafe definition.

### Security

- Default loopback port publication, exact inbound Host validation, explicit CORS origins, and a single backend owner per database.
- Shared HTTP/Webhook destination checks, default-empty outbound allowlist, HTTPS defaults, DNS/IP restrictions, and disabled redirects/environment proxies.
- Controlled public errors, parameterized SQLite operations, bounded execution output, and history output storage disabled by default.
- AI remains optional and inactive by default; Mock generation requires no key, network, external SDK, or model download.

### Known Limitations

- No built-in user authentication, multi-user collaboration, or public deployment security configuration.
- SQLite persistence and a single-instance scheduler; no distributed execution or Exactly-Once guarantee.
- Synchronous Execute has no live node streaming or cancellation API. A lost connection can leave the outcome unknown; automatic retry is unsafe.
- No live AI provider integrations, AI workflow nodes, tool calling, or model execution.
- Docker runtime acceptance covers Ubuntu 24.04 CI. The local Windows machine has no Docker Engine; other host platforms and architectures were not verified.
- Private vulnerability reporting verification covers the enabled setting and public entry only; end-to-end submission, notification delivery, and actual receipt were not tested.
- Two recorded P2 issues remain: stale execution details can be affected by canvas node selection after deletion, and an extreme history offset can produce a controlled 500 rather than 422.
- Historical node IDs truncated by an older implementation cannot be reliably reconstructed. History is not a full workflow snapshot, and basic redaction cannot identify all secrets in text.

See [RELEASE_CHECKLIST.md](docs/RELEASE_CHECKLIST.md) for the current decision and the [Phase 07A audit](docs/PHASE_07A_AUDIT.md) for reproducible issue details.

## Versioning

The initial version is `0.1.0`. The `0.1.x` line is early development: API and workflow formats may still need changes, which should be documented with migration guidance when applicable. `1.0.0` will be considered only after more stable public contracts are established; no date or long-term compatibility guarantee is promised.
