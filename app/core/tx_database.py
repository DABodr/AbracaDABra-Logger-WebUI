"""TX database loader for AbracaDABra TII data.

Refactored from map_acadabra.py
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Optional

import pandas as pd


def split_tii_to_main_sub(tii_val) -> tuple[int | None, int | None]:
    """Parse TII value to main/sub identifiers.

    Examples:
        '0101' -> (1, 1)
        '1204' -> (12, 4)
        '304'  -> (3, 4)  # auto zfill
    """
    if tii_val is None:
        return None, None
    s = "".join(ch for ch in str(tii_val).strip() if ch.isdigit())
    if not s:
        return None, None
    s = s.zfill(4)
    try:
        return int(s[:2]), int(s[2:])
    except Exception:
        return None, None


def format_tii_code(main: int, sub: int) -> str:
    """Format main/sub as TII code string in decimal format.

    TII codes are always formatted as MMSS in decimal (e.g., main=67 sub=2 -> "6702").

    Examples:
        (1, 1) -> '0101'
        (12, 4) -> '1204'
        (67, 2) -> '6702'
    """
    return f"{main:02d}{sub:02d}"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points using Haversine formula."""
    R = 6371.0  # Earth's radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def calculate_azimuth(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate azimuth (bearing) from point 1 to point 2 in degrees."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    bearing = math.atan2(x, y)
    return (math.degrees(bearing) + 360) % 360


def _read_tx_csv_robust(tx_path: Path) -> pd.DataFrame:
    """Robust reading of dab-tx-list.csv.

    Handles:
    - Trailing semicolons on each line
    - BOM characters
    - Encoding issues
    """
    with open(tx_path, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        header = [h.strip() for h in header if h is not None]

        # Strip BOM if present
        if header and header[0].startswith("\ufeff"):
            header[0] = header[0].replace("\ufeff", "")

        rows = []
        for r in reader:
            if not r:
                continue
            # Drop last empty field if present (trailing semicolon)
            if len(r) == len(header) + 1 and (r[-1] == "" or r[-1] is None):
                r = r[:-1]
            # Skip malformed rows
            if len(r) != len(header):
                continue
            rows.append(r)

    return pd.DataFrame(rows, columns=header)


class TXDatabase:
    """TX database manager."""

    def __init__(self):
        self._df: Optional[pd.DataFrame] = None
        self._path: Optional[Path] = None
        self._mtime: float = 0

    def is_loaded(self) -> bool:
        """Check if database is loaded."""
        return self._df is not None and not self._df.empty

    def is_stale(self, tx_path: Path) -> bool:
        """Check if database needs reloading."""
        if self._path != tx_path:
            return True
        if self._df is None:
            return True
        try:
            current_mtime = tx_path.stat().st_mtime
            return current_mtime != self._mtime
        except Exception:
            return True

    def load(self, tx_path: Path, force: bool = False) -> pd.DataFrame:
        """Load TX database from CSV file.

        Args:
            tx_path: Path to dab-tx-list.csv
            force: Force reload even if cached

        Returns:
            DataFrame with TX data
        """
        if not force and not self.is_stale(tx_path):
            return self._df

        if not tx_path.exists():
            raise FileNotFoundError(f"TX database not found: {tx_path}")

        tx = _read_tx_csv_robust(tx_path)
        tx.columns = [c.strip() for c in tx.columns]

        # Check required columns
        required = ["block", "eid", "tii", "location", "latidec", "longidec"]
        missing = [c for c in required if c not in tx.columns]
        if missing:
            raise ValueError(f"Missing TX columns: {missing}. Available: {tx.columns.tolist()}")

        # Normalize columns
        tx["block"] = tx["block"].str.strip().str.upper()
        tx["eid"] = tx["eid"].str.strip().str.upper()

        # Parse TII to main/sub
        tx[["main", "sub"]] = tx["tii"].apply(lambda v: pd.Series(split_tii_to_main_sub(v)))
        tx["main"] = tx["main"].astype("Int64")
        tx["sub"] = tx["sub"].astype("Int64")

        # Parse coordinates
        tx["lat"] = pd.to_numeric(tx["latidec"].str.replace(",", ".", regex=False), errors="coerce")
        tx["lon"] = pd.to_numeric(tx["longidec"].str.replace(",", ".", regex=False), errors="coerce")

        # Optional columns
        if "ensemblelabel" in tx.columns:
            tx["ensemble_label"] = tx["ensemblelabel"].astype(str).str.strip()
        else:
            tx["ensemble_label"] = ""

        if "erp" in tx.columns:
            tx["erp_kw"] = pd.to_numeric(tx["erp"].str.replace(",", ".", regex=False), errors="coerce")
        else:
            tx["erp_kw"] = None

        # Filter valid rows
        tx = tx[tx["lat"].notna() & tx["lon"].notna()].copy()
        tx = tx[tx["main"].notna() & tx["sub"].notna()].copy()
        tx = tx[tx["eid"].map(lambda x: len(str(x).strip()) == 4)].copy()

        # Cast to proper int
        tx["main"] = tx["main"].astype(int)
        tx["sub"] = tx["sub"].astype(int)

        # Add TII code column
        tx["tii_code"] = tx.apply(lambda r: format_tii_code(r["main"], r["sub"]), axis=1)

        # Cache
        self._df = tx
        self._path = tx_path
        self._mtime = tx_path.stat().st_mtime

        return tx

    def get_dataframe(self) -> pd.DataFrame | None:
        """Get the loaded DataFrame."""
        return self._df

    def find_tx(self, block: str, eid: str, main: int, sub: int) -> pd.Series | None:
        """Find a specific transmitter by identifiers."""
        if self._df is None:
            return None

        mask = (
            (self._df["block"] == block.upper()) &
            (self._df["eid"] == eid.upper()) &
            (self._df["main"] == main) &
            (self._df["sub"] == sub)
        )
        matches = self._df[mask]
        if len(matches) > 0:
            return matches.iloc[0]
        return None


# Global instance
_tx_db = TXDatabase()


def get_tx_database() -> TXDatabase:
    """Get the global TX database instance."""
    return _tx_db


def load_tx_database(tx_path: Path, force: bool = False) -> pd.DataFrame:
    """Load TX database (convenience function)."""
    return _tx_db.load(tx_path, force=force)
