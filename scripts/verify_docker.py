"""CI-only acceptance of the real Compose services using disposable, isolated data."""

import argparse
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = "http://127.0.0.1:5173"
BACKEND = "http://127.0.0.1:8000"
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def api(path, payload=None, *, method="GET", status=200, base=FRONTEND):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base + path, data=body, method=method,
                                     headers={"Content-Type": "application/json"})
    with HTTP.open(request, timeout=60) as response:
        require(response.status == status, "Unexpected API status")
        return json.load(response)


def wait_for_health():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if all(api("/api/health", base=base) == {"status": "ok"}
                   for base in (FRONTEND, BACKEND)):
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(1)
    raise RuntimeError("Backend and production frontend did not become healthy")


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    run_id, attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(os.environ.get("GITHUB_ACTIONS") == "true" and
            re.fullmatch(r"\d+", run_id) and re.fullmatch(r"\d+", attempt),
            "This script runs only in the GitHub Actions acceptance job")
    project = f"flowpilot-ci-{run_id}-{attempt}"
    require(os.environ.get("COMPOSE_PROJECT_NAME") == project, "Unexpected Compose project")
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve()
    require(runner_temp.is_dir(), "RUNNER_TEMP must exist")
    with tempfile.TemporaryDirectory(prefix="flowpilot-docker-", dir=runner_temp) as temporary:
        directory = Path(temporary)
        data = directory / "data"
        data.mkdir()
        override = directory / "compose.json"
        override.write_text(json.dumps({"services": {"backend": {"volumes": [
            {"type": "bind", "source": str(data), "target": "/app/data"}
        ]}}}), encoding="utf-8")
        command = ["docker", "compose", "--project-name", project,
                   "--project-directory", str(ROOT), "-f", str(ROOT / "docker-compose.yml"),
                   "-f", str(override)]

        def compose(*arguments, check=True):
            result = subprocess.run(command + list(arguments), cwd=ROOT, text=True,
                                    capture_output=True, timeout=180)
            if check and result.returncode:
                # Only this disposable project is used; no credentials are supplied.
                print((result.stdout + result.stderr)[-16000:], flush=True)
                result.check_returncode()
            return result

        configuration = json.loads(compose("config", "--format", "json").stdout)
        for service in ("backend", "frontend"):
            ports = configuration["services"][service]["ports"]
            require(ports and all(p.get("host_ip") == "127.0.0.1" for p in ports),
                    "Published ports must remain loopback-only")
        mounts = configuration["services"]["backend"]["volumes"]
        require(len(mounts) == 1 and Path(mounts[0]["source"]).resolve() == data.resolve()
                and mounts[0]["target"] == "/app/data", "Data bind must be isolated")
        require(not list(data.iterdir()), "Acceptance data must be fresh")
        try:
            compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "120")
            wait_for_health()
            with HTTP.open(FRONTEND + "/", timeout=10) as page:
                require("text/html" in page.headers.get("Content-Type", "") and
                        b'<div id="root">' in page.read(262144), "Production HTML is unavailable")
            original_id = compose("ps", "-q", "backend").stdout.split()
            require(len(original_id) == 1, "Expected exactly one backend owner")
            manual = json.loads((ROOT / "examples/workflows/manual-logger.json").read_text())
            saved = api("/api/workflows", manual, method="POST", status=201)
            path = f"/api/workflows/{saved['id']}"
            validation = api(path + "/validate", method="POST")
            require(validation["structural"]["valid"] and
                    validation["execution_readiness"]["valid"], "Manual example is invalid")
            result = api(path + "/execute", method="POST")
            require(result["status"] == "success" and
                    all(n["status"] == "success" for n in result["node_results"]),
                    "Manual example did not succeed")
            execution_path = f"/api/executions/{result['execution_id']}"
            detail = api(execution_path)
            require(detail["outputs_stored"] is False and
                    all(n["output"] is None for n in detail["node_results"]),
                    "Default history must not persist outputs")
            scheduled = json.loads((ROOT / "examples/workflows/scheduled-logger.json").read_text())
            # Annual trigger at least a day away, avoiding calendar-boundary races.
            future = datetime.now(UTC) + timedelta(days=2)
            scheduled["definition"]["nodes"][0]["config"]["cron"] = (
                f"0 0 {future.day} {future.month} *")
            schedule = api("/api/workflows", scheduled, method="POST", status=201)
            schedule_path = f"/api/workflows/{schedule['id']}/schedule"
            require(api(schedule_path)["enabled"] is False, "Imported schedule must be disabled")
            state = api(schedule_path, {"enabled": True}, method="PUT")
            require(state["scheduler_running"] and state["next_run_at"] and state["enabled"],
                    "Schedule was not admitted")

            def verify_persistence():
                wait_for_health()
                require(api(path) == saved, "Workflow changed after container lifecycle operation")
                history = api(path + "/executions")
                require(history["total"] == 1 and
                        history["items"][0]["execution_id"] == result["execution_id"],
                        "Execution history was lost or replayed")
                require(api(execution_path) == detail, "Stored execution detail changed")
                restored = api(schedule_path)
                require(restored["enabled"] and restored["scheduler_running"] and
                        restored["next_run_at"] and restored["last_error"] is None,
                        "Enabled schedule was not restored")
                require(api(f"/api/workflows/{schedule['id']}/executions")["total"] == 0,
                        "Future schedule unexpectedly executed")
                require(len(compose("ps", "-q", "backend").stdout.split()) == 1,
                        "Multiple backend owners were created")

            compose("stop", "backend")
            compose("start", "--wait", "backend")
            verify_persistence()
            compose("up", "-d", "--no-build", "--no-deps", "--force-recreate",
                    "--wait", "--wait-timeout", "120", "backend")
            require(compose("ps", "-q", "backend").stdout.split() != original_id,
                    "Backend container was not recreated")
            verify_persistence()
            api(schedule_path, {"enabled": False}, method="PUT")
            require((data / "flowpilot.db").stat().st_size > 0, "SQLite data is missing")
            print("PASS Docker startup, proxy/API, execution/history, persistent data, restart and schedule recovery")
        except Exception:
            logs = compose("logs", "--no-color", "--tail", "80", check=False)
            print(logs.stdout[-16000:], flush=True)
            raise
        finally:
            compose("down", "--remove-orphans", "--timeout", "20")


if __name__ == "__main__":
    main()
