# Example workflows

These files are `POST /api/workflows` request bodies using Workflow Definition
schema version 1. They contain no API keys, private URLs, AI nodes or outgoing
webhook deliveries. FlowPilot does not currently have a JSON file-import button:
use the existing API to save an example, then open it from the Dashboard.

| File | Flow | Initial status |
| --- | --- | --- |
| [manual-logger.json](manual-logger.json) | Manual Trigger → Logger A → Logger B | Ready for a manual run; no external service required |
| [scheduled-logger.json](scheduled-logger.json) | Schedule Trigger → Logger | Saved with the schedule **disabled**; explicit enable is required |
| [api-condition.json](api-condition.json) | Manual → HTTP Request → Condition → true/false Logger | **Setup required**: outbound HTTP is denied by the default empty allowlist |

Structural validation and executable readiness are different. The general
`/validate` report checks graph rules; it does not replace the stricter
configuration and policy checks performed by Execute or Schedule Enable.

## Save an example

Start FlowPilot using the [project setup instructions](../../README.md). From
the repository root, macOS/Linux users can save the offline manual example with:

```bash
curl -X POST http://127.0.0.1:8000/api/workflows \
  -H 'Content-Type: application/json' \
  --data-binary @examples/workflows/manual-logger.json
```

Windows PowerShell:

```powershell
$examplePath = (Resolve-Path examples/workflows/manual-logger.json).Path
$workflow = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/workflows -ContentType application/json -Body ([System.IO.File]::ReadAllBytes($examplePath))
```

The response supplies a new workflow UUID. Refresh the Dashboard and select
**Open Editor**, or open `/editor?id=<workflow UUID>` on the frontend. Saving an
example does not execute it. Change the filename in the command to save another
example; each POST creates a separate workflow.

## Manual logger

After saving, click **Run Workflow** in the editor with no unsaved changes.
The three nodes should finish successfully. The Logger executor passes through
its direct upstream inputs; it does not write payload text to a log file.
Logger B's live output is:

```json
{
  "logger_a": {
    "manual": { "trigger": "manual" }
  }
}
```

Open **History** and **View Details** to inspect the same execution. History does
not store node outputs by default, so its output fields can be null even though
the live result contains data. This example needs neither AI nor external HTTP.

## Scheduled logger

The trigger stores `*/5 * * * *` with timezone `UTC`. Schedule management state
is separate from the Definition; there is deliberately no unsupported `enabled`
field in the JSON file. A new workflow is disabled, has no Next Run, and is not
registered as a runnable scheduler job merely by importing it.

To opt in, save the example, open the editor's **Schedule** tab, then click
**Enable Schedule**. The backend validates the saved configuration. Dispatch and
a Next Run time require the backend scheduler to be running; the browser can be
closed. With `FLOWPILOT_SCHEDULER_ENABLED=false`, enabled state can still be saved,
but the API reports `scheduler_running=false` and `next_run_at=null`. Use
**Disable Schedule** to stop future dispatches. Manual Run does not run Schedule
Trigger workflows.

Equivalent API operations, replacing the UUID with the one returned on save:

```bash
workflow_id='REPLACE_WITH_RETURNED_UUID'
curl -X PUT "http://127.0.0.1:8000/api/workflows/$workflow_id/schedule" \
  -H 'Content-Type: application/json' --data '{"enabled":true}'
curl "http://127.0.0.1:8000/api/workflows/$workflow_id/schedule"
curl -X PUT "http://127.0.0.1:8000/api/workflows/$workflow_id/schedule" \
  -H 'Content-Type: application/json' --data '{"enabled":false}'
```

Do not enable schedules until their timing and effects have been reviewed.
Keep one backend process and one scheduler owner, as described in the project
documentation.

## API condition — setup required

This example makes one GET to `https://httpbin.org/json`. The Condition checks
whether `body.slideshow.title` exists in the HTTP node's successful JSON output.
Only the matching `true` or `false` connection activates its Logger; the other
Logger is skipped. Both branches pass through the Condition result, not the
entire HTTP response. Public service availability and response structure can
change; review them before using this as a live integration.

The default `FLOWPILOT_HTTP_ALLOWED_HOSTS=[]` blocks this example before any
request. For a fresh local setup that you choose to run, add only the reviewed
destination to the backend environment:

```dotenv
FLOWPILOT_HTTP_ALLOWED_HOSTS='["httpbin.org"]'
```

For Docker Compose, update the root `.env` and run
`docker compose up -d --force-recreate backend` to apply the changed environment;
`docker compose restart` alone does not reload it. For native development,
restart the backend process with the updated variable.

If you already have a host list, preserve its reviewed entries rather than
blindly replacing it. This is the **outbound** HTTP destination allowlist;
`FLOWPILOT_ALLOWED_HOSTS` instead protects incoming Host headers. Do not disable
HTTPS, public-address/DNS checks, redirects, timeout or size limits to run the
example. An allowed hostname still has to satisfy those restrictions.

Run only after saving and completing this explicit setup. A graph-valid example
can still receive Execute 422 because of policy or configuration, or return a
failed execution because the public service is unavailable. No real service
success is assumed by the automated tests.

## Validation

The release example tests parse these exact files, save and validate all three
through the existing API, run the manual example, and verify that importing the
scheduled example leaves it disabled. HTTP tests retain the default denial and
then use Mock Transport with a controlled public DNS answer to exercise both
Condition branches without external requests or notifications:

```bash
cd backend
.venv/bin/python -m pytest tests/test_release_examples.py -q
```

On Windows use `.venv\Scripts\python.exe` instead. Tests use temporary databases
and never touch the project's `data/flowpilot.db`.
