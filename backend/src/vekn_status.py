"""In-process status tracking for VEKN sync/push jobs; resets on restart by design."""

from datetime import UTC, datetime

# job key -> {last_success_at, last_error_at, last_error, last_status, last_detail}
_status: dict[str, dict] = {}


def record_success(job: str, detail: dict | None = None) -> None:
    entry = _status.setdefault(job, {})
    entry["last_success_at"] = datetime.now(UTC).isoformat()
    entry["last_status"] = "ok"
    if detail is not None:
        entry["last_detail"] = detail


def record_error(job: str, message: str) -> None:
    """Keeps last_success_at for contrast."""
    entry = _status.setdefault(job, {})
    entry["last_error_at"] = datetime.now(UTC).isoformat()
    entry["last_error"] = message
    entry["last_status"] = "error"


def get_status() -> dict[str, dict]:
    return _status
