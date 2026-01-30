"""Configuration API routes."""

from __future__ import annotations

import ftplib
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...config import (
    get_config,
    update_config,
    AppConfig,
    TelegramConfig,
    FTPConfig,
    PathsConfig,
    RXConfig,
)
from ..models.config import (
    AppConfigRequest,
    TelegramConfigRequest,
    FTPConfigRequest,
    PathsConfigRequest,
    RXConfigRequest,
    FTPTestResponse,
)

router = APIRouter(prefix="/api/config", tags=["config"])


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
        "ftp": {
            "server": config.ftp.server,
            "username": config.ftp.username,
            "password": "***" if config.ftp.password else "",
            "remote_dir": config.ftp.remote_dir,
            "remote_filename": config.ftp.remote_filename,
            "enabled": config.ftp.enabled,
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
        config.telegram = TelegramConfig(
            token=request.telegram.token or config.telegram.token,
            allowed_chats=request.telegram.allowed_chats,
            poll_interval_sec=request.telegram.poll_interval_sec,
            enabled=request.telegram.enabled,
        )

    if request.ftp is not None:
        config.ftp = FTPConfig(
            server=request.ftp.server,
            username=request.ftp.username,
            password=request.ftp.password if request.ftp.password else config.ftp.password,
            remote_dir=request.ftp.remote_dir,
            remote_filename=request.ftp.remote_filename,
            enabled=request.ftp.enabled,
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


@router.get("/ftp")
async def get_ftp_config():
    """Get FTP configuration."""
    config = get_config()
    return {
        "server": config.ftp.server,
        "username": config.ftp.username,
        "password": "***" if config.ftp.password else "",
        "remote_dir": config.ftp.remote_dir,
        "remote_filename": config.ftp.remote_filename,
        "enabled": config.ftp.enabled,
    }


@router.put("/ftp")
async def update_ftp_config(request: FTPConfigRequest):
    """Update FTP configuration."""
    config = get_config()
    config.ftp = FTPConfig(
        server=request.server,
        username=request.username,
        password=request.password if request.password and request.password != "***" else config.ftp.password,
        remote_dir=request.remote_dir,
        remote_filename=request.remote_filename,
        enabled=request.enabled,
    )
    update_config(config)
    return {"success": True}


@router.post("/test-ftp", response_model=FTPTestResponse)
async def test_ftp_connection(request: FTPConfigRequest) -> FTPTestResponse:
    """Test FTP connection."""
    if not request.server or not request.username:
        return FTPTestResponse(success=False, message="Server and username required")

    # Get password from config if not provided
    password = request.password
    if not password or password == "***":
        config = get_config()
        password = config.ftp.password

    if not password:
        return FTPTestResponse(success=False, message="Password required")

    try:
        ftp = ftplib.FTP(request.server, timeout=10)
        ftp.login(request.username, password)

        if request.remote_dir and request.remote_dir != "/":
            ftp.cwd(request.remote_dir)

        ftp.quit()
        return FTPTestResponse(success=True, message="Connection successful")

    except ftplib.error_perm as e:
        return FTPTestResponse(success=False, message=f"Permission error: {e}")
    except ftplib.error_temp as e:
        return FTPTestResponse(success=False, message=f"Temporary error: {e}")
    except Exception as e:
        return FTPTestResponse(success=False, message=f"Connection failed: {e}")


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
