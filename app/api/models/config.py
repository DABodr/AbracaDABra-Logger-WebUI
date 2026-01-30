"""Pydantic models for configuration API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TelegramConfigRequest(BaseModel):
    """Telegram configuration update request."""
    token: str = ""
    allowed_chats: str = ""
    poll_interval_sec: int = Field(default=20, ge=5, le=300)
    enabled: bool = False


class FTPConfigRequest(BaseModel):
    """FTP configuration update request."""
    server: str = ""
    username: str = ""
    password: str = ""
    remote_dir: str = "/"
    remote_filename: str = "abracadabra_dx.html"
    enabled: bool = False


class PathsConfigRequest(BaseModel):
    """Paths configuration update request."""
    csv_dir: str
    tx_db_path: str
    out_dir: str


class RXConfigRequest(BaseModel):
    """RX location configuration update request."""
    name: str = "My Receiver"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AppConfigRequest(BaseModel):
    """Full application configuration update request."""
    telegram: TelegramConfigRequest | None = None
    ftp: FTPConfigRequest | None = None
    paths: PathsConfigRequest | None = None
    rx: RXConfigRequest | None = None
    refresh_interval_sec: int | None = Field(None, ge=15, le=3600)
    auto_refresh_enabled: bool | None = None


class FTPTestResponse(BaseModel):
    """FTP connection test response."""
    success: bool
    message: str


class StatusResponse(BaseModel):
    """System status response."""
    status: str  # "online", "error", "warning"
    last_csv_file: str | None = None
    last_csv_time: str | None = None
    mux_count: int = 0
    tii_count: int = 0
    last_error: str | None = None
    telegram_running: bool = False
    uptime_seconds: int = 0
