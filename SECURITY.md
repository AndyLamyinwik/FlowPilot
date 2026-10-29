# Security Policy

## Deployment Boundary

FlowPilot v0.1.0 is an **unreleased Early Public Release candidate** with no built-in user authentication. Its defaults are intended for a local machine or a trusted environment. **Do not expose the unauthenticated API or frontend directly to the public Internet.**

Compose publishes both services only on `127.0.0.1`. If a deployment uses an external reverse proxy, the operator must provide authentication, TLS, and network access controls. Host validation and CORS are not authorization mechanisms.

Workflows can execute outbound HTTP requests and webhooks after the operator explicitly permits destinations. Treat permission to create or execute a workflow as permission to cause those external effects. Closing the browser or losing an Execute connection does not cancel backend work; check execution history before trying again.

## Vulnerability Reporting

**GitHub Private Vulnerability Reporting is enabled for [AndyLamyinwik/FlowPilot](https://github.com/AndyLamyinwik/FlowPilot).** The repository setting and public reporting entry were verified on **2026-10-30**.

To report a potential vulnerability privately:

1. Sign in to GitHub and open [Report a vulnerability](https://github.com/AndyLamyinwik/FlowPilot/security/advisories/new). You can also open the repository's **Security → Advisories** page and choose **Report a vulnerability**.
2. Describe the affected candidate/version or commit, impact, environment, and safe minimal reproduction steps. Remove credentials, personal data, private URLs, and unrelated workflow output.
3. Submit through GitHub's private reporting form rather than a public Issue or pull request. Repository owners may see advisory-management controls instead of the external reporter's entry.

Do not publish vulnerability details, exploit code, private data, credentials, or unredacted workflow outputs in public Issues or pull requests. No security email address or separate support channel is provided by this policy. There is no response-time or remediation SLA at this stage.

Verification covered the saved enabled setting and the **Report a vulnerability** link visible on the public Advisories page. **No test report or advisory was submitted; notification delivery and actual report receipt were not tested.** Enabling the route is not a full security audit or release approval. See the [release checklist](docs/RELEASE_CHECKLIST.md) for the remaining gates.

## Supported Versions

| Version | Status |
| --- | --- |
| `0.1.0` development candidate | Current candidate under preparation; not yet released |
| Earlier released versions | No release history verified in this checkout |

Security fixes are evaluated against the current development candidate. No long-term support policy or support for future versions is promised. The `0.1.x` line is early development, and public interfaces may still change.

## Configuration and Secrets

- Keep inbound `FLOWPILOT_ALLOWED_HOSTS` restricted to exact deployment hostnames/IPs. The default includes local names and the internal Compose `backend` name; do not replace it with a wildcard.
- Outbound `FLOWPILOT_HTTP_ALLOWED_HOSTS` is a separate policy. It defaults to an empty list, so HTTP/Webhook destinations are denied until explicitly allowed. An allowed hostname must still pass the HTTP client's other restrictions.
- Never store API keys, passwords, cookies, or Authorization headers in workflow JSON. Do not commit `.env`, credentials, private keys, runtime SQLite data, backups, or logs.
- Inspect execution outputs and logs before sharing them. Basic key-based redaction cannot recognize every secret in arbitrary text.
- If a credential is exposed, revoke or rotate it with the relevant provider. Removing a file or adding `.gitignore` does not remove a secret from an existing Git history; coordinate any history cleanup with the maintainer rather than rewriting it without approval.

## Network Safety

HTTP and Outgoing Webhook share the same application client and restrictions: explicit exact-host allowlist, HTTPS by default, public-address checks, validation of DNS answers, pinned connection targets, no redirects or environment proxy use, and bounded time/size settings. Do not disable these controls globally to reach a test service.

These checks are not a complete SSRF guarantee or network sandbox. Synchronous DNS and an already-running I/O operation cannot always be interrupted immediately. Deployment-level DNS, routing, TLS trust, and egress controls still matter. Tests using controlled transports do not establish that every real network topology or container environment is safe.

## Execution and Data Safety

- Run one backend process, one scheduler owner, and one Uvicorn worker per database. This is not a distributed scheduler or cross-process Exactly-Once system.
- Do not interpret workflow configuration or model output as Python, Shell, dynamic imports, or arbitrary local file operations.
- History does not store node inputs or full workflow configuration. Outputs are excluded by default; optional output storage applies basic redaction and record-size limits, which do not guarantee that all sensitive content has been removed.
- Keep database files and backups private. Stop all writers before an offline backup; do not delete SQLite journals or instance lock files to bypass an error.
- Interrupted executions are recorded for inspection, not automatically replayed. External effects and history writes cannot be made atomic by the current architecture.

## AI Status

Only a deterministic development/test Mock Provider exists. There are no live OpenAI, Anthropic/Claude, Gemini, or Ollama integrations, no AI node executor, and no public AI API. `FLOWPILOT_AI_ENABLED` defaults to false; setting it to true does not enable a real adapter.

The provider contracts and registry are not a sandbox for arbitrary Python code. Future adapters must be trusted, must obtain credentials from safe backend sources, and must not gain direct control over workflow storage, scheduling, or system commands. See the [AI Provider Guide](docs/AI_PROVIDER_GUIDE.md).

## Verification Limits

The [release checklist](docs/RELEASE_CHECKLIST.md) is the authority for current release evidence. Docker image execution/container recreation and remote GitHub Actions were not established by the preceding local validation. A local passing test suite is not a full security audit or approval to deploy publicly.
