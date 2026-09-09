# -*- coding: utf-8 -*-
"""Fixed-path headless BOQ export job contract.

The native Agent Bridge creates the queued request. The regular pyRevit BOQ
command consumes it inside Revit, so the existing classifier, quantity engine
and XLSX writer remain the only export implementation.
"""

import io
import json
import os
import re
import time


JOB_SCHEMA = "rcc-boq-agent-export-job/1.0.0"
MAX_JOB_BYTES = 64 * 1024
_JOB_ID = re.compile(r"^[a-fA-F0-9-]{32,36}$")


def agent_export_root():
    local_root = os.environ.get("LOCALAPPDATA", "")
    if not local_root:
        return ""
    return os.path.join(local_root, "RCC_BOQ", "AgentExports")


def agent_export_job_path():
    local_root = os.environ.get("LOCALAPPDATA", "")
    if not local_root:
        return ""
    return os.path.join(local_root, "RCC_BOQ", "boq_export_job.json")


def _is_safe_output_path(path):
    root = agent_export_root()
    if not root or not path:
        return False
    root_value = os.path.normcase(os.path.abspath(root))
    path_value = os.path.normcase(os.path.abspath(path))
    return (
        path_value.startswith(root_value + os.sep)
        and path_value.lower().endswith(".xlsx")
    )


def _write_job(job):
    path = agent_export_job_path()
    if not path:
        raise IOError("Agent export job directory is unavailable")
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    payload = json.dumps(job, indent=2, sort_keys=True)
    if len(payload.encode("utf-8")) > MAX_JOB_BYTES:
        raise ValueError("Agent export job exceeds the configured limit")
    temporary_path = path + ".tmp"
    with io.open(temporary_path, "w", encoding="utf-8") as job_file:
        job_file.write(payload)
    if os.path.exists(path):
        os.remove(path)
    os.rename(temporary_path, path)


def load_queued_export_job(document_title):
    """Return a validated queued job for this exact active document."""
    path = agent_export_job_path()
    if not path or not os.path.isfile(path):
        return None
    if os.path.getsize(path) <= 0 or os.path.getsize(path) > MAX_JOB_BYTES:
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as job_file:
            job = json.load(job_file)
    except Exception:
        return None
    if not isinstance(job, dict):
        return None
    if job.get("schema") != JOB_SCHEMA or job.get("status") != "queued":
        return None
    job_id = str(job.get("job_id", ""))
    if not _JOB_ID.match(job_id):
        return None
    if str(job.get("document_title", "")) != str(document_title or ""):
        return None
    if job.get("export_format") not in ("classic", "site"):
        return None
    if not _is_safe_output_path(job.get("output_path", "")):
        return None
    return job


def mark_export_job_running(job):
    job["status"] = "running"
    job["started_at_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job["error"] = ""
    _write_job(job)


def complete_export_job(job, validation_report):
    job["status"] = "completed"
    job["completed_at_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job["error"] = ""
    job["validation"] = {
        "ok": bool(validation_report.get("ok")),
        "workbook_name": str(validation_report.get("workbook_name", ""))[:250],
        "workbook_sha256": str(validation_report.get("workbook_sha256", ""))[:64],
        "expected_sheet_count": int(validation_report.get("expected_sheet_count", 0)),
        "actual_sheet_count": int(validation_report.get("actual_sheet_count", 0)),
        "expected_cell_count": int(validation_report.get("expected_cell_count", 0)),
        "actual_cell_count": int(validation_report.get("actual_cell_count", 0)),
        "mismatch_count": int(validation_report.get("mismatch_count", 0)),
    }
    _write_job(job)


def fail_export_job(job, error):
    job["status"] = "failed"
    job["completed_at_utc"] = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job["error"] = str(error or "Headless BOQ export failed")[:500]
    _write_job(job)
