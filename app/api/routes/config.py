"""Configuration API routes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...config import (
    get_config,
    update_config,
    AppConfig,
    TelegramConfig,
    PathsConfig,
    RXConfig,
)
from ..models.config import (
    AppConfigRequest,
    TelegramConfigRequest,
    PathsConfigRequest,
    RXConfigRequest,
)

router = APIRouter(prefix="/api/config", tags=["config"])


def _hash_password(password: str) -> str:
    """Hash a password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


class PasswordRequest(BaseModel):
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@router.get("/password-status")
async def get_password_status():
    """Check if a config password is set."""
    config = get_config()
    return {"has_password": bool(config.config_password_hash)}


@router.post("/verify-password")
async def verify_password(req: PasswordRequest):
    """Verify the config access password."""
    config = get_config()
    if not config.config_password_hash:
        return {"success": True}
    if _hash_password(req.password) == config.config_password_hash:
        return {"success": True}
    return {"success": False, "message": "Mot de passe incorrect"}


@router.post("/set-password")
async def set_password(req: PasswordChangeRequest):
    """Set or change the config password."""
    config = get_config()
    # If a password already exists, verify the current one
    if config.config_password_hash:
        if _hash_password(req.current_password) != config.config_password_hash:
            return {"success": False, "message": "Mot de passe actuel incorrect"}
    if req.new_password:
        config.config_password_hash = _hash_password(req.new_password)
    else:
        config.config_password_hash = ""
    update_config(config)
    return {"success": True, "message": "Mot de passe mis à jour"}


@router.get("")
async def get_configuration():
    """Get full application configuration."""
    config = get_config()
    # Don't expose password in response
    return {
        "telegram": {
            "token": config.telegram.token[:10] + "..." if config.telegram.token else "",
            "allowed_chats": config.telegram.allowed_chats,
            "poll_interval_sec": config.telegram.poll_interval_sec,
            "enabled": config.telegram.enabled,
        },
        "paths": {
            "csv_dir": config.paths.csv_dir,
            "tx_db_path": config.paths.tx_db_path,
            "out_dir": config.paths.out_dir,
        },
        "rx": {
            "name": config.rx.name,
            "lat": config.rx.lat,
            "lon": config.rx.lon,
        },
        "refresh_interval_sec": config.refresh_interval_sec,
        "auto_refresh_enabled": config.auto_refresh_enabled,
    }


@router.put("")
async def update_configuration(request: AppConfigRequest):
    """Update application configuration."""
    config = get_config()

    if request.telegram is not None:
        # Keep existing token if the submitted value is masked or empty
        new_token = request.telegram.token
        if not new_token or new_token.endswith("..."):
            new_token = config.telegram.token
        config.telegram = TelegramConfig(
            token=new_token,
            allowed_chats=request.telegram.allowed_chats,
            poll_interval_sec=request.telegram.poll_interval_sec,
            enabled=request.telegram.enabled,
        )

    if request.paths is not None:
        config.paths = PathsConfig(
            csv_dir=request.paths.csv_dir,
            tx_db_path=request.paths.tx_db_path,
            out_dir=request.paths.out_dir,
        )

    if request.rx is not None:
        config.rx = RXConfig(
            name=request.rx.name,
            lat=request.rx.lat,
            lon=request.rx.lon,
        )

    if request.refresh_interval_sec is not None:
        config.refresh_interval_sec = request.refresh_interval_sec

    if request.auto_refresh_enabled is not None:
        config.auto_refresh_enabled = request.auto_refresh_enabled

    update_config(config)

    return {"success": True, "message": "Configuration updated"}


@router.get("/telegram")
async def get_telegram_config():
    """Get Telegram configuration."""
    config = get_config()
    return {
        "token": config.telegram.token[:10] + "..." if config.telegram.token else "",
        "allowed_chats": config.telegram.allowed_chats,
        "poll_interval_sec": config.telegram.poll_interval_sec,
        "enabled": config.telegram.enabled,
    }


@router.put("/telegram")
async def update_telegram_config(request: TelegramConfigRequest):
    """Update Telegram configuration."""
    config = get_config()
    config.telegram = TelegramConfig(
        token=request.token or config.telegram.token,
        allowed_chats=request.allowed_chats,
        poll_interval_sec=request.poll_interval_sec,
        enabled=request.enabled,
    )
    update_config(config)
    return {"success": True}


@router.get("/paths")
async def get_paths_config():
    """Get paths configuration."""
    config = get_config()
    return {
        "csv_dir": config.paths.csv_dir,
        "tx_db_path": config.paths.tx_db_path,
        "out_dir": config.paths.out_dir,
        "csv_dir_exists": Path(config.paths.csv_dir).exists(),
        "tx_db_exists": Path(config.paths.tx_db_path).exists(),
        "out_dir_exists": Path(config.paths.out_dir).exists(),
    }


@router.put("/paths")
async def update_paths_config(request: PathsConfigRequest):
    """Update paths configuration."""
    config = get_config()
    config.paths = PathsConfig(
        csv_dir=request.csv_dir,
        tx_db_path=request.tx_db_path,
        out_dir=request.out_dir,
    )
    update_config(config)

    # Clear cache when paths change
    from ...core.csv_parser import clear_cache
    clear_cache()

    return {"success": True}


@router.get("/rx")
async def get_rx_config():
    """Get RX location configuration."""
    config = get_config()
    return {
        "name": config.rx.name,
        "lat": config.rx.lat,
        "lon": config.rx.lon,
    }


@router.put("/rx")
async def update_rx_config(request: RXConfigRequest):
    """Update RX location configuration."""
    config = get_config()
    config.rx = RXConfig(
        name=request.name,
        lat=request.lat,
        lon=request.lon,
    )
    update_config(config)
    return {"success": True}


@router.get("/browse")
async def browse_filesystem(
    path: str = Query(default="~", description="Starting path"),
    mode: str = Query(default="dir", description="Mode: 'dir' for directories, 'file' for files"),
    filter_ext: Optional[str] = Query(default=None, description="File extension filter (e.g., '.csv')")
):
    """Browse filesystem to select directories or files."""
    try:
        # Expand ~ to home directory
        browse_path = Path(path).expanduser().resolve()

        if not browse_path.exists():
            # Fall back to home directory
            browse_path = Path.home()

        if not browse_path.is_dir():
            browse_path = browse_path.parent

        items = []

        # Add parent directory entry if not at root
        if browse_path.parent != browse_path:
            items.append({
                "name": "..",
                "path": str(browse_path.parent),
                "is_dir": True,
                "size": None,
            })

        # List directory contents
        try:
            entries = sorted(browse_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            entries = []

        for entry in entries:
            # Skip hidden files
            if entry.name.startswith("."):
                continue

            try:
                is_dir = entry.is_dir()

                # Apply filter based on mode
                if mode == "dir" and not is_dir:
                    # In directory mode, also show files matching filter for selection
                    if filter_ext and not entry.name.endswith(filter_ext):
                        continue
                elif mode == "file" and not is_dir:
                    # In file mode, filter by extension if specified
                    if filter_ext and not entry.name.endswith(filter_ext):
                        continue

                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_dir": is_dir,
                    "size": entry.stat().st_size if not is_dir else None,
                })
            except (PermissionError, OSError):
                continue

        return {
            "current_path": str(browse_path),
            "items": items,
            "can_select": mode == "dir" or (mode == "file" and any(not i["is_dir"] for i in items)),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
