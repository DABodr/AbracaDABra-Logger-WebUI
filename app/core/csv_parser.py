"""CSV parser for AbracaDABra scan files.

Refactored from abracadabra_dx_bot.py
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# DAB channel to frequency mapping (MHz)
DAB_FREQUENCIES: dict[str, float] = {
    "5A": 174.928, "5B": 176.640, "5C": 178.352, "5D": 180.064,
    "6A": 181.936, "6B": 183.648, "6C": 185.360, "6D": 187.072,
    "7A": 188.928, "7B": 190.640, "7C": 192.352, "7D": 194.064,
    "8A": 195.936, "8B": 197.648, "8C": 199.360, "8D": 201.072,
    "9A": 202.928, "9B": 204.640, "9C": 206.352, "9D": 208.064,
    "10A": 209.936, "10B": 211.648, "10C": 213.360, "10D": 215.072,
    "10N": 210.096,
    "11A": 216.928, "11B": 218.640, "11C": 220.352, "11D": 222.064,
    "11N": 217.088,
    "12A": 223.936, "12B": 225.648, "12C": 227.360, "12D": 229.072,
    "12N": 224.096,
    "13A": 230.784, "13B": 232.496, "13C": 234.208, "13D": 235.776,
    "13E": 237.488, "13F": 239.200,
}


def get_frequency_mhz(channel: str) -> float:
    """Get frequency in MHz for a DAB channel."""
    return DAB_FREQUENCIES.get(channel.upper().strip(), 0.0)


def is_dab_block(text: str) -> bool:
    """Check if text is a valid DAB block identifier."""
    return bool(re.match(r"^\d{1,2}[A-Z]$", text.strip().upper()))


def channel_sort_key(ch: str) -> tuple:
    """Sort key for DAB channels (numeric then letter)."""
    ch = (ch or "").strip().upper()
    try:
        return (int(ch[:-1]), ch[-1])
    except Exception:
        return (999, ch)


def detect_time_column(df: pd.DataFrame) -> str | None:
    """Detect the time column in a DataFrame (handles language variations)."""
    for c in df.columns:
        if str(c).strip().lower().startswith("time"):
            return c
    return None


def ueid_to_eid4(ueid: str) -> str:
    """Convert UEID to 4-digit EID.

    Example: E1F043 -> F043
    """
    s = str(ueid).strip().upper()
    hex_only = "".join(ch for ch in s if ch in "0123456789ABCDEF")
    if len(hex_only) >= 4:
        return hex_only[-4:]
    return s[-4:] if len(s) >= 4 else s


def safe_parse_int(x) -> int | None:
    """Safely parse an integer value."""
    try:
        return int(float(str(x).strip().replace(",", ".")))
    except Exception:
        return None


def to_float(x) -> float | None:
    """Safely convert value to float."""
    try:
        return float(str(x).strip().replace(",", "."))
    except Exception:
        return None


class CSVCache:
    """Cache for parsed CSV data with modification time tracking."""

    def __init__(self):
        self._cache: dict[Path, pd.DataFrame] = {}
        self._mtimes: dict[Path, float] = {}
        self._raw_cache: dict[Path, pd.DataFrame] = {}

    def is_stale(self, csv_path: Path) -> bool:
        """Check if cached data is stale."""
        if csv_path not in self._mtimes:
            return True
        try:
            current_mtime = csv_path.stat().st_mtime
            return current_mtime != self._mtimes[csv_path]
        except Exception:
            return True

    def get_processed(self, csv_path: Path) -> pd.DataFrame | None:
        """Get processed (deduplicated) DataFrame from cache."""
        if not self.is_stale(csv_path):
            return self._cache.get(csv_path)
        return None

    def get_raw(self, csv_path: Path) -> pd.DataFrame | None:
        """Get raw DataFrame from cache."""
        if not self.is_stale(csv_path):
            return self._raw_cache.get(csv_path)
        return None

    def set(self, csv_path: Path, raw_df: pd.DataFrame, processed_df: pd.DataFrame) -> None:
        """Store DataFrames in cache."""
        try:
            self._mtimes[csv_path] = csv_path.stat().st_mtime
            self._cache[csv_path] = processed_df
            self._raw_cache[csv_path] = raw_df
        except Exception:
            pass

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()
        self._mtimes.clear()
        self._raw_cache.clear()


# Global cache instance
_csv_cache = CSVCache()


def choose_latest_abraca_csv(csv_dir: Path) -> Path | None:
    """Find the latest valid AbracaDABra CSV file.

    Looks for CSV files with required columns: Label, Channel, Location, SNR [dB]
    """
    if not csv_dir.exists():
        return None

    files = sorted(csv_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)

    for f in files[:20]:
        # Skip TX database if it's in the same directory
        if f.name.lower() == "dab-tx-list.csv":
            continue

        try:
            head = pd.read_csv(f, sep=";", nrows=1, encoding="utf-8")
            required = {"Label", "Channel", "Location", "SNR [dB]"}
            if required.issubset(head.columns):
                return f
        except Exception:
            continue

    return None


def parse_csv(csv_path: Path, use_cache: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    """Parse AbracaDABra CSV file.

    Returns:
        Tuple of (raw_df, processed_df, time_column_name)
        - raw_df: All rows from CSV
        - processed_df: Deduplicated rows with best SNR per (Location, Channel, Label)
    """
    if use_cache:
        processed = _csv_cache.get_processed(csv_path)
        raw = _csv_cache.get_raw(csv_path)
        if processed is not None and raw is not None:
            time_col = detect_time_column(raw)
            return raw, processed, time_col

    # Read CSV
    df = pd.read_csv(csv_path, sep=";", skipinitialspace=True, encoding="utf-8")

    time_col = detect_time_column(df)
    if not time_col:
        raise ValueError(f"Time column not found. Columns: {list(df.columns)}")

    # Strip whitespace from string columns
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)

    # Convert numeric columns
    df["SNR [dB]"] = pd.to_numeric(df.get("SNR [dB]"), errors="coerce")
    df["Distance [km]"] = pd.to_numeric(df.get("Distance [km]"), errors="coerce")

    for col in ["Power [kW]", "Level [dB]", "Azimuth [deg]"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ["Main", "Sub"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Parse time column
    df[time_col] = pd.to_datetime(df[time_col], errors="coerce")

    # Add derived columns
    if "UEID" in df.columns:
        df["eid"] = df["UEID"].apply(ueid_to_eid4)

    if "Channel" in df.columns:
        df["frequency_mhz"] = df["Channel"].apply(get_frequency_mhz)

    raw_df = df.copy()

    # Deduplicate: keep best SNR per (Location, Channel, Label)
    group_cols = ["Location", "Channel", "Label"]
    idx_best = df.groupby(group_cols)["SNR [dB]"].idxmax()
    df_best = df.loc[idx_best].copy()

    # Add SNR statistics
    stats = df.groupby(group_cols)["SNR [dB]"].agg(SNR_min="min", SNR_max="max").reset_index()
    df_best = df_best.merge(stats, on=group_cols, how="left")

    # Sort by channel then SNR
    df_best["Channel"] = pd.Categorical(
        df_best["Channel"],
        categories=sorted(df_best["Channel"].dropna().unique(), key=channel_sort_key),
        ordered=True
    )
    df_best = df_best.sort_values(["Channel", "SNR_max"], ascending=[True, False])

    # Cache results
    if use_cache:
        _csv_cache.set(csv_path, raw_df, df_best)

    return raw_df, df_best, time_col


def get_services_count(raw_df: pd.DataFrame, channel: str, label: str) -> int:
    """Get the count of unique services for a mux."""
    if "Services" in raw_df.columns:
        mask = (raw_df["Channel"] == channel) & (raw_df["Label"] == label)
        services = raw_df.loc[mask, "Services"].dropna().unique()
        if len(services) > 0:
            try:
                return int(services[0])
            except (ValueError, TypeError):
                pass
    return 0


def clear_cache() -> None:
    """Clear the CSV cache."""
    _csv_cache.clear()
