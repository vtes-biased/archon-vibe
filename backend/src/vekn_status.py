"""In-process status tracking for VEKN sync/push jobs (observability).

A days-long vekn.net outage is otherwise invisible except in logs. The scheduled
jobs (member sync, tournament sync, hourly batch_push) record their last success
and last error here; an IC-gated admin endpoint exposes the snapshot so admins
can see at a glance whether sync/push is healthy.

State is module-level and resets on restart — by design: "is it working right
now" is the question, not a durable audit trail (logs remain the record).
"""

from datetime import UTC, datetime

# job key -> {last_success_at, last_error_at, last_error, last_status, last_detail}
_status: dict[str, dict] = {}


def record_success(job: str, detail: dict | None = None) -> None:
    """Record that `job` just completed successfully."""
    entry = _status.setdefault(job, {})
    entry["last_success_at"] = datetime.now(UTC).isoformat()
    entry["last_status"] = "ok"
    if detail is not None:
        entry["last_detail"] = detail


def record_error(job: str, message: str) -> None:
    """Record that `job` just failed (keeps last_success_at for contrast)."""
    entry = _status.setdefault(job, {})
    entry["last_error_at"] = datetime.now(UTC).isoformat()
    entry["last_error"] = message
    entry["last_status"] = "error"


def get_status() -> dict[str, dict]:
    """Return the full status snapshot (per-job last success/error)."""
    return _status
