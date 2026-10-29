import hashlib
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import RLock
from uuid import UUID

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler

from app.db.database import Database
from app.db.schedules import ScheduleRepository
from app.db.workflows import WorkflowRepository
from app.schemas.schedule import ScheduleRead
from app.schemas.workflow import ValidationIssue
from app.services.execution.schedule_node import parse_schedule
from app.services.execution.validation import ExecutionValidationError
from app.services.execution_service import ExecutionConflict, ExecutionService, WorkflowNotFound

logger = logging.getLogger("flowpilot.scheduler")


class SchedulerService:
    """Single-process scheduler; SQLite is authoritative, jobs are reconstructible."""

    def __init__(
        self,
        database: Database,
        execution_service: ExecutionService,
        *,
        enabled: bool = True,
        workers: int = 4,
        scheduler: BackgroundScheduler | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if type(workers) is not int or not 1 <= workers <= 32:
            raise ValueError("Scheduler worker count must be between 1 and 32")
        if type(enabled) is not bool:
            raise ValueError("Scheduler enabled must be a boolean")
        self.repository = ScheduleRepository(database)
        self.workflows = WorkflowRepository(database)
        self.execution_service = execution_service
        self.enabled = enabled
        self.clock = clock if clock is not None else lambda: datetime.now(UTC)
        self.scheduler = scheduler if scheduler is not None else BackgroundScheduler(
            timezone=UTC,
            executors={"default": ThreadPoolExecutor(max_workers=workers)},
            job_defaults={"coalesce": True, "misfire_grace_time": 60, "max_instances": 1},
        )
        self._lock = RLock()
        self._started = False
        self._closed = False
        self._stopping = False
        self._fingerprints: dict[UUID, str] = {}
        # If an in-memory operation fails, block callbacks until resynchronization.
        self._quarantined: set[UUID] = set()
        self.scheduler.add_listener(
            self._on_event, EVENT_JOB_ERROR | EVENT_JOB_MAX_INSTANCES | EVENT_JOB_MISSED
        )

    @staticmethod
    def job_id(workflow_id: UUID) -> str:
        return f"workflow:{workflow_id}"

    @contextmanager
    def mutation(self) -> Iterator[None]:
        """Serialize short management changes, never the workflow execution itself."""
        with self._lock:
            yield

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self._closed:
                raise RuntimeError("Scheduler service is already closed")
            self._started = True
            if not self.enabled:
                logger.info("Scheduler disabled by configuration")
                return
            try:
                self.scheduler.start(paused=True)
                self.reconcile()
                self.scheduler.add_job(
                    self._cleanup, "interval", minutes=1, id="history:cleanup", replace_existing=True,
                    coalesce=True, misfire_grace_time=60, max_instances=1,
                )
                self.scheduler.add_job(
                    self._reconcile_safely, "interval", minutes=1,
                    id="schedules:reconcile", replace_existing=True,
                    coalesce=True, misfire_grace_time=60, max_instances=1,
                )
                self.scheduler.resume()
            except Exception:
                self._started = False
                self._stopping = True
                if self.scheduler.running:
                    self.scheduler.shutdown(wait=False)
                raise
        logger.info("Scheduler started; enabled schedules restored without offline catch-up")

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._stopping = True
            running = self.scheduler.running
            if running:
                self.scheduler.pause()
        # A running callback can briefly acquire _lock; do not hold it while joining.
        if running:
            self.scheduler.shutdown(wait=True)
        with self._lock:
            self._started = False
            self._closed = True
        logger.info("Scheduler stopped")

    def _validate(self, workflow_id: UUID):
        record = self.workflows.get(workflow_id)
        if record is None:
            raise WorkflowNotFound()
        snapshot = self.execution_service.engine_factory().validate(
            record.definition, trigger_type="schedule"
        )
        nodes = [node for node in snapshot.nodes if node.type == "trigger.schedule"]
        if len(nodes) != 1:
            raise ExecutionValidationError([
                ValidationIssue(
                    code="INVALID_SCHEDULE_TRIGGER", message="Workflow requires one schedule trigger"
                )
            ])
        parsed, trigger = parse_schedule(nodes[0].config)
        fingerprint = hashlib.sha256(
            json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
            .encode("utf-8")
        ).hexdigest()
        return parsed, trigger, fingerprint

    def _remove_job(self, workflow_id: UUID) -> bool:
        try:
            self.scheduler.remove_job(self.job_id(workflow_id))
        except JobLookupError:
            pass
        except Exception:
            self._quarantined.add(workflow_id)
            logger.error("Schedule job removal failed workflow_id=%s", workflow_id)
            return False
        self._fingerprints.pop(workflow_id, None)
        return True

    def _sync(self, workflow_id: UUID) -> None:
        """Rebuild one job after database commit, failing closed on memory errors."""
        state = self.repository.get(workflow_id)
        if state is None or not state.enabled:
            if self._remove_job(workflow_id):
                self._quarantined.discard(workflow_id)
            elif state is not None:
                self.repository.set_enabled(
                    workflow_id, False, last_error="SCHEDULE_SYNC_FAILED"
                )
            return
        try:
            _, trigger, fingerprint = self._validate(workflow_id)
        except (ExecutionValidationError, WorkflowNotFound):
            self._quarantined.add(workflow_id)
            if self.workflows.get(workflow_id) is not None:
                self.repository.set_enabled(
                    workflow_id, False, last_error="SCHEDULE_INVALID_WORKFLOW"
                )
            else:
                self.repository.delete(workflow_id)
            self._remove_job(workflow_id)
            logger.warning("Schedule disabled: invalid workflow workflow_id=%s", workflow_id)
            return
        if not self.enabled or not self._started or self._stopping:
            return
        try:
            if (
                self._fingerprints.get(workflow_id) != fingerprint
                or self.scheduler.get_job(self.job_id(workflow_id)) is None
            ):
                self.scheduler.add_job(
                    self.run_workflow, trigger,
                    args=[workflow_id], id=self.job_id(workflow_id),
                    replace_existing=True, coalesce=True, misfire_grace_time=60,
                    max_instances=1,
                )
                self._fingerprints[workflow_id] = fingerprint
            self._quarantined.discard(workflow_id)
        except Exception:
            self._quarantined.add(workflow_id)
            # SQLite and APScheduler are not one transaction. Disable durable
            # state so even an old job still present cannot execute a workflow.
            self.repository.set_enabled(workflow_id, False, last_error="SCHEDULE_SYNC_FAILED")
            self._remove_job(workflow_id)
            logger.error("Schedule synchronization failed workflow_id=%s", workflow_id)

    def reconcile(self) -> None:
        with self._lock:
            enabled = {record.workflow_id for record in self.repository.list_enabled()}
            # Remove stale jobs as well as registering missing enabled schedules.
            for job in self.scheduler.get_jobs():
                if not job.id.startswith("workflow:"):
                    continue
                try:
                    workflow_id = UUID(job.id.removeprefix("workflow:"))
                except ValueError:
                    continue
                if workflow_id not in enabled:
                    if self._remove_job(workflow_id):
                        self._quarantined.discard(workflow_id)
            for workflow_id in sorted(enabled, key=str):
                try:
                    self._sync(workflow_id)
                except Exception:
                    self._quarantined.add(workflow_id)
                    logger.error("Schedule recovery failed workflow_id=%s", workflow_id)

    def get(self, workflow_id: UUID) -> ScheduleRead:
        with self._lock:
            record = self.workflows.get(workflow_id)
            if record is None:
                raise WorkflowNotFound()
            state = self.repository.get(workflow_id)
            cron = timezone = None
            raw = record.definition if isinstance(record.definition, dict) else {}
            nodes = raw.get("nodes", [])
            nodes = nodes if isinstance(nodes, list) else []
            schedule_nodes = [node for node in nodes if isinstance(node, dict) and node.get("type") == "trigger.schedule"]
            if len(schedule_nodes) == 1:
                try:
                    parsed, _ = parse_schedule(schedule_nodes[0].get("config", {}))
                    cron, timezone = parsed.cron, parsed.timezone
                except Exception:
                    pass
            job = self.scheduler.get_job(self.job_id(workflow_id)) if self.scheduler.running else None
            running = self.enabled and self._started and not self._stopping and self.scheduler.running
            active = state is not None and state.enabled and workflow_id not in self._quarantined
            return ScheduleRead(
                workflow_id=workflow_id, enabled=state.enabled if state else False,
                cron=cron, timezone=timezone,
                next_run_at=job.next_run_time if job is not None and running and active else None,
                scheduler_running=running,
                last_error=state.last_error if state else None,
            )

    def set_enabled(self, workflow_id: UUID, enabled: bool) -> ScheduleRead:
        with self._lock:
            if self.workflows.get(workflow_id) is None:
                raise WorkflowNotFound()
            if enabled:
                self._validate(workflow_id)
            self.repository.set_enabled(workflow_id, enabled)
            self._sync(workflow_id)
            return self.get(workflow_id)

    def workflow_updated(self, workflow_id: UUID) -> ScheduleRead:
        with self._lock:
            self._sync(workflow_id)
            return self.get(workflow_id)

    def workflow_deleted(self, workflow_id: UUID) -> None:
        with self._lock:
            self._quarantined.add(workflow_id)
            if self._remove_job(workflow_id):
                self._quarantined.discard(workflow_id)

    def _eligible(self, workflow_id: UUID) -> bool:
        with self._lock:
            if (
                not self.enabled or not self._started or self._stopping
                or workflow_id in self._quarantined
            ):
                return False
            state = self.repository.get(workflow_id)
            return state is not None and state.enabled

    def run_workflow(self, workflow_id: UUID) -> None:
        """APScheduler callback; reload state and snapshot at execution admission."""
        try:
            if not self._eligible(workflow_id):
                logger.info("Scheduled execution skipped: disabled workflow_id=%s", workflow_id)
                return
            self.execution_service.execute(
                workflow_id, trigger_type="schedule", scheduled_at=self.clock().astimezone(UTC),
                run_if=lambda: self._eligible(workflow_id),
            )
        except ExecutionConflict:
            logger.warning("Scheduled execution skipped: active workflow_id=%s", workflow_id)
        except WorkflowNotFound:
            logger.info("Scheduled execution skipped: deleted workflow_id=%s", workflow_id)
        except ExecutionValidationError:
            # Workflow may have been changed between admission and snapshot.
            try:
                with self._lock:
                    self._sync(workflow_id)
            except Exception:
                logger.error("Schedule invalidation failed workflow_id=%s", workflow_id)
            logger.warning("Scheduled execution rejected: invalid workflow_id=%s", workflow_id)
        except Exception:
            # Never expose exception text; it can include URLs, outputs or SQL.
            logger.error("Scheduled execution callback failed workflow_id=%s", workflow_id)

    def _cleanup(self) -> None:
        try:
            count = self.execution_service.history.cleanup()
            logger.info("History retention completed deleted=%s", count)
        except Exception:
            logger.error("History retention failed")

    def _reconcile_safely(self) -> None:
        try:
            self.reconcile()
        except Exception:
            logger.error("Schedule reconciliation failed")

    def _on_event(self, event) -> None:
        # Do not log event.exception or traceback: executor output is untrusted.
        reason = {
            EVENT_JOB_MISSED: "misfire",
            EVENT_JOB_MAX_INSTANCES: "max_instances",
            EVENT_JOB_ERROR: "job_error",
        }.get(event.code, "scheduler_event")
        logger.warning("Scheduler event reason=%s job_id=%s", reason, event.job_id)
