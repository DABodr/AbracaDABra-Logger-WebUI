"""Configuration management for AbracaDABra Logger WebUI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "config.json"


class TelegramConfig(BaseModel):
    """Telegram bot configuration."""
    token: str = Field(default="", description="Telegram bot token")
    allowed_chats: str = Field(default="", description="Comma-separated allowed chat IDs")
    poll_interval_sec: int = Field(default=20, ge=5, le=300)
    enabled: bool = Field(default=False)


class PathsConfig(BaseModel):
    """File paths configuration."""
    csv_dir: str = Field(
        default=str(Path.home() / "Documents"),
        description="Directory containing AbracaDABra CSV scan files"
    )
    tx_db_path: str = Field(
        default=str(Path.home() / "AppData" / "Local" / "AbracaDABra" / "cache" / "TII" / "dab-tx-list.csv"),
        description="Path to TX database (dab-tx-list.csv)"
    )
    out_dir: str = Field(
        default=str(Path.home() / "Documents" / "AbracadradabExport"),
        description="Output directory for generated files"
    )


class RXConfig(BaseModel):
    """Receiver location configuration."""
    name: str = Field(default="My Receiver")
    lat: float = Field(default=49.768, ge=-90, le=90)
    lon: float = Field(default=4.72, ge=-180, le=180)


class AppConfig(BaseModel):
    """Main application configuration."""
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    rx: RXConfig = Field(default_factory=RXConfig)
    refresh_interval_sec: int = Field(default=120, ge=15, le=3600)
    auto_refresh_enabled: bool = Field(default=True)
    config_password_hash: str = Field(default="", description="SHA-256 hash of config access password")


def load_config() -> AppConfig:
    """Load configuration from file or create default."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return AppConfig.model_validate(data)
        except Exception:
            pass

    # Try to load from environment variables (legacy support)
    config = AppConfig()

    if os.getenv("ABRACA_TG_TOKEN"):
        config.telegram.token = os.getenv("ABRACA_TG_TOKEN", "")
        config.telegram.allowed_chats = os.getenv("ABRACA_TG_ALLOWED", "")
        config.telegram.poll_interval_sec = int(os.getenv("ABRACA_TG_POLL_SEC", "20"))
        config.telegram.enabled = bool(config.telegram.token)

    if os.getenv("ABRACA_CSV_DIR"):
        config.paths.csv_dir = os.getenv("ABRACA_CSV_DIR", config.paths.csv_dir)

    if os.getenv("ABRACA_OUT_DIR"):
        config.paths.out_dir = os.getenv("ABRACA_OUT_DIR", config.paths.out_dir)

    if os.getenv("ABRACA_REFRESH_MIN"):
        config.refresh_interval_sec = int(os.getenv("ABRACA_REFRESH_MIN", "2")) * 60

    return config


def save_config(config: AppConfig) -> None:
    """Save configuration to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        config.model_dump_json(indent=2),
        encoding="utf-8"
    )


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def update_config(new_config: AppConfig) -> AppConfig:
    """Update and save configuration."""
    global _config
    save_config(new_config)
    _config = new_config
    return _config
