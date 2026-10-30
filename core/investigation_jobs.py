"""In-memory investigation jobs for live progress polling."""

from __future__ import annotations

import threading
import time
import uuid
from copy import deepcopy
from typing import Any, Optional

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_JOB_TTL_SEC = 3600

DEFAULT_STEPS: list[dict[str, str]] = [
    {"id": "init", "text": "Initializing investigation case", "meta": "", "state": "pending"},
    {"id": "parse", "text": "Parsing ledger variance", "meta": "", "state": "pending"},
    {"id": "search", "text": "Searching evidence locker", "meta": "", "state": "pending"},
    {"id": "rank", "text": "Ranking candidate evidence", "meta": "", "state": "pending"},
    {"id": "crossref", "text": "Cross-referencing source systems", "meta": "", "state": "pending"},
    {"id": "chain", "text": "Building evidence chain", "meta": "", "state": "pending"},
    {"id": "analyze", "text": "Running forensic analysis model", "meta": "", "state": "pending"},
    {"id": "remediation", "text": "Drafting recommended remediation", "meta": "", "state": "pending"},
    {"id": "report", "text": "Generating audit-ready report", "meta": "", "state": "pending"},
]


def _prune_old_jobs() -> None:
    now = time.time()
    stale = [jid for jid, j in _jobs.items() if now - j.get("updated_at", 0) > _JOB_TTL_SEC]
    for jid in stale:
        _jobs.pop(jid, None)


def create_job() -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _prune_old_jobs()
        _jobs[job_id] = {
            "status": "running",
            "steps": deepcopy(DEFAULT_STEPS),
            "report": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
    return job_id


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        return {
            "status": job["status"],
            "steps": deepcopy(job["steps"]),
            "report": job.get("report"),
            "error": job.get("error"),
        }


def set_job_error(job_id: str, message: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "error"
        job["error"] = message
        job["updated_at"] = time.time()


def set_job_done(job_id: str, report: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "done"
        job["report"] = report
        job["updated_at"] = time.time()


class InvestigationProgress:
    """Updates job steps as the investigator runs."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def _sync_steps(self, steps: list[dict[str, str]]) -> None:
        with _lock:
            job = _jobs.get(self.job_id)
            if job:
                job["steps"] = deepcopy(steps)
                job["updated_at"] = time.time()

    def activate(self, step_id: str, meta: str = "") -> None:
        job = get_job(self.job_id)
        if not job:
            return
        steps = job["steps"]
        for step in steps:
            if step["id"] == step_id:
                step["state"] = "active"
                if meta:
                    step["meta"] = meta
            elif step["state"] == "active":
                step["state"] = "done"
        self._sync_steps(steps)

    def complete(self, step_id: str, meta: Optional[str] = None) -> None:
        job = get_job(self.job_id)
        if not job:
            return
        steps = job["steps"]
        for step in steps:
            if step["id"] == step_id:
                step["state"] = "done"
                if meta is not None:
                    step["meta"] = meta
        self._sync_steps(steps)
