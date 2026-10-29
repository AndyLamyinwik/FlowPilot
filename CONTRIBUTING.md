# Contributing to FlowPilot

## Welcome

FlowPilot is a lightweight, local-first workflow automation project. Contributions that improve correctness, usability, documentation, tests, and deployment are welcome. Keep changes focused and discuss substantial features before implementing them. Not every proposal or pull request will be accepted.

The first candidate is **0.1.0, an unreleased Early Public Release**. Check the [release checklist](docs/RELEASE_CHECKLIST.md) for current blockers. No paid editor, AI service, or development tool is required.

## Development Setup

### Get the source

Clone [AndyLamyinwik/FlowPilot](https://github.com/AndyLamyinwik/FlowPilot) for local development:

```bash
git clone https://github.com/AndyLamyinwik/FlowPilot.git flowpilot
cd flowpilot
git switch -c fix/short-description
```

For a pull request, fork the project and clone your fork instead. If you already have a local checkout, keep any existing changes and use its normal branch workflow. Do not reset or clean someone else's work.

### Requirements

- Python 3.12 or newer.
- Node.js 24.15 or newer within the 24.x line.
- npm 11 or 12; the recorded package manager is npm 11.21.1.
- Docker Engine/Desktop with Compose for container checks; native development can run without Docker.

Copy `.env.example` to `.env` in the project root only if `.env` does not already exist. Preserve local settings and compare new options manually. Never commit `.env` or credentials.

### Backend

From the project root, on Windows PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install --require-hashes -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

On macOS/Linux:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-dev.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Use one backend process and one scheduler owner per database. Do not use multiple workers or production reload. Restart the native process after backend changes. The health endpoint is [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health); interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

### Frontend

In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). To check the production frontend instead, stop the development server and run:

```bash
npm run build
npm start
```

`npm start` serves `dist/` with the built-in Node server and reads the root `.env` through Node's native optional env-file support. `VITE_API_BASE_URL` is public build-time configuration; changing it requires a rebuild. `API_PROXY_TARGET` is server-only runtime configuration. Neither belongs in workflow business code.

### Run tests

From `backend/`:

```powershell
.\.venv\Scripts\python -m pytest -q --tb=short
```

On macOS/Linux, use `.venv/bin/python -m pytest -q --tb=short`. Tests must use isolated databases and controlled HTTP transports, not the user's runtime data or real third-party services.

From `frontend/`:

```bash
npm test
npm run test:server
npm run typecheck
npm run build
```

From the root, validate container configuration:

```bash
docker compose config --quiet
```

When Docker is available and the change affects deployment, also verify builds and connectivity in an explicitly isolated Compose project with its own data directory. Never test destructive operations against the default runtime database or delete a volume to make a test pass. Record unavailable checks as not tested.

CI runs backend tests, frontend checks, and Docker configuration/build checks. Local success does not imply that GitHub Actions has run; report both separately.

## Project Structure

| Directory | Responsibility |
| --- | --- |
| `backend/app/api/` | HTTP routes and API boundaries |
| `backend/app/core/` | Settings, logging, and instance ownership |
| `backend/app/db/` | SQLite lifecycle and repositories |
| `backend/app/schemas/` | Pydantic workflow and API contracts |
| `backend/app/services/` | Validation, execution, scheduler, and history |
| `backend/app/ai/` | Independent provider contracts and offline Mock only |
| `frontend/src/` | React pages, reusable components, API services, and types |
| `examples/workflows/` | Candidate release workflow examples |
| `docs/` | Architecture, guides, audits, and release verification |
| `data/` | Ignored local runtime data; never use it as a test fixture |

Read [AGENTS.md](AGENTS.md) and the [architecture guide](docs/ARCHITECTURE.md) before changing module boundaries.

## Development Guidelines

- Keep HTTP routes, repositories, business services, and node execution logic separate. Preserve existing API behavior and workflow JSON compatibility; discuss any required migration explicitly.
- Keep Metadata Registry and Executor Registry responsibilities separate. Do not register an unfinished node or expose a fake capability.
- Preserve Explicit Save, drafts, node/edge identities, Condition handles, branch activation, fail-fast behavior, and execution isolation.
- Use parameterized SQL and short transactions. Initialization must preserve existing data. Workflow execution must not hold a SQLite write transaction.
- Preserve default loopback deployment, exact Host allowlists, HTTP/Webhook restrictions, safe errors, and output privacy. Do not weaken controls to make tests pass.
- Add meaningful regression tests for bugs and appropriate tests for accepted features. Never delete a failing test or change its expected result to conceal a defect.
- Avoid unnecessary dependencies. Pin direct versions and regenerate the appropriate lockfile when an approved dependency change is needed; do not edit resolver output by hand.
- AI is optional and currently Mock-only. No key, model download, or paid API may be required by a test. Model output must never become arbitrary Python/Shell execution.
- Update relevant documentation and `docs/PROJECT_STATUS.md`, including actual validation results and limitations. Keep unrelated refactors out of the change.

## Pull Requests

1. Fork [AndyLamyinwik/FlowPilot](https://github.com/AndyLamyinwik/FlowPilot) and create a focused feature/fix branch.
2. Describe the problem or agreed feature, then implement the smallest maintainable change.
3. Run related tests and the required type/build/deployment checks.
4. Review the diff for private data, generated artifacts, accidental API changes, and unrelated files.
5. Open a pull request with the resulting behavior, reproduction steps where useful, commands/results, and any remaining risks or untested areas.

Do not include `.env`, API keys, SQLite files, logs, local caches, `node_modules`, or build output. Do not publish images or releases as part of a contribution unless the maintainers explicitly authorize that separate action.

## Bug Reports

For non-security bugs, use [GitHub Issues](https://github.com/AndyLamyinwik/FlowPilot/issues). Include:

- A concise description and minimal reproduction steps.
- Expected and actual behavior.
- Candidate/version or commit, operating system, Python/Node versions, and native/Docker setup.
- Relevant error codes and sanitized logs or minimal workflow data.
- Whether the problem occurs consistently and any workaround.

Remove credentials, private URLs, personal data, and sensitive execution outputs before sharing. Do not report exploitable vulnerabilities publicly; follow [SECURITY.md](SECURITY.md).

## Feature Requests

Explain the use case, expected behavior, and a small example. State how it fits the project's lightweight, self-hosted design. A proposal starts a discussion; it is not a commitment to implement or accept a pull request.

## License

Contributions are intended for the project's existing [MIT License](LICENSE). Keep appropriate third-party notices and verify the licensing of any code or assets you add. The project's license does not replace the separate terms of its dependencies.
