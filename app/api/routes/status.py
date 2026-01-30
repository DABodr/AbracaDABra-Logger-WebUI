"""Status API routes."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from ...config import get_config
from ...core.csv_parser import choose_latest_abraca_csv
from ..models.config import StatusResponse

router = APIRouter(prefix="/api/status", tags=["status"])

# Track startup time
_start_time = time.time()

# Global state for status tracking
_state = {
    "last_csv_file": None,
    "last_csv_time": None,
    "mux_count": 0,
    "tii_count": 0,
    "last_error": None,
    "telegram_running": False,
}


def update_status(
    csv_file: str | None = None,
    mux_count: int | None = None,
    tii_count: int | None = None,
    error: str | None = None,
    telegram_running: bool | None = None,
):
    """Update global status state."""
    if csv_file is not None:
        _state["last_csv_file"] = csv_file
        _state["last_csv_time"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    if mux_count is not None:
        _state["mux_count"] = mux_count
    if tii_count is not None:
        _state["tii_count"] = tii_count
    if error is not None:
        _state["last_error"] = error
    elif error == "":
        _state["last_error"] = None
    if telegram_running is not None:
        _state["telegram_running"] = telegram_running


def clear_error():
    """Clear the last error."""
    _state["last_error"] = None


@router.get("", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Get system status."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)

    # Check if we can find a CSV file
    status = "online"
    if _state["last_error"]:
        status = "error"
    elif not csv_dir.exists():
        status = "warning"
    else:
        csv_file = choose_latest_abraca_csv(csv_dir)
        if csv_file is None:
            status = "warning"

    uptime = int(time.time() - _start_time)

    return StatusResponse(
        status=status,
        last_csv_file=_state["last_csv_file"],
        last_csv_time=_state["last_csv_time"],
        mux_count=_state["mux_count"],
        tii_count=_state["tii_count"],
        last_error=_state["last_error"],
        telegram_running=_state["telegram_running"],
        uptime_seconds=uptime,
    )


@router.get("/csv-files")
async def list_csv_files():
    """List available CSV files."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)

    if not csv_dir.exists():
        return {"files": [], "error": f"Directory not found: {csv_dir}"}

    files = []
    for f in sorted(csv_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        try:
            stat = f.stat()
            files.append({
                "name": f.name,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M:%S"),
                "size_kb": round(stat.st_size / 1024, 1),
            })
        except Exception:
            continue

    return {"files": files, "directory": str(csv_dir)}
