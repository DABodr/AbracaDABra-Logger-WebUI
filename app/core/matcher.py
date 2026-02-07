"""RX/TX matching logic.

Matches received signals (RX) with transmitter database (TX)
using (block, eid, main, sub) as the join key.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .csv_parser import parse_csv, ueid_to_eid4
from .tx_database import get_tx_database, haversine_km, calculate_azimuth


def prepare_rx_for_matching(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare RX DataFrame for matching with TX database.

    Adds normalized columns: block, eid, main, sub
    """
    df = raw_df.copy()

    # Normalize block/channel
    if "Channel" in df.columns:
        df["block"] = df["Channel"].astype(str).str.strip().str.upper()

    # Convert UEID to EID
    if "UEID" in df.columns:
        df["eid"] = df["UEID"].apply(ueid_to_eid4)
    elif "eid" not in df.columns:
        df["eid"] = ""

    # Parse main/sub as nullable integers - do NOT fillna(0) to avoid inventing TII values
    if "Main" in df.columns:
        df["main"] = pd.to_numeric(df["Main"], errors="coerce").astype("Int64")
    else:
        df["main"] = pd.NA

    if "Sub" in df.columns:
        df["sub"] = pd.to_numeric(df["Sub"], errors="coerce").astype("Int64")
    else:
        df["sub"] = pd.NA

    # Filter rows with valid matching keys (main=0 is valid, so use notna())
    df = df[
        (df["block"].str.len() > 0) &
        (df["eid"].str.len() == 4) &
        df["main"].notna() &
        df["sub"].notna()
    ].copy()

    return df


def match_rx_tx(rx_df: pd.DataFrame, tx_df: pd.DataFrame) -> pd.DataFrame:
    """Match RX data with TX database.

    Args:
        rx_df: RX DataFrame (from prepare_rx_for_matching)
        tx_df: TX DataFrame (from TXDatabase.load)

    Returns:
        Matched DataFrame with columns from both RX and TX
    """
    keys = ["block", "eid", "main", "sub"]

    # Perform inner join
    matched = rx_df.merge(tx_df, on=keys, how="inner", suffixes=("_rx", "_tx"))

    return matched


def enrich_with_distance(
    matched_df: pd.DataFrame,
    rx_lat: float,
    rx_lon: float
) -> pd.DataFrame:
    """Add distance and azimuth from RX to each TX.

    Args:
        matched_df: Matched DataFrame
        rx_lat: Receiver latitude
        rx_lon: Receiver longitude

    Returns:
        DataFrame with distance_km and azimuth_deg columns
    """
    df = matched_df.copy()

    def calc_distance(row):
        if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
            return haversine_km(rx_lat, rx_lon, row["lat"], row["lon"])
        return None

    def calc_azimuth(row):
        if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
            return calculate_azimuth(rx_lat, rx_lon, row["lat"], row["lon"])
        return None

    df["distance_km"] = df.apply(calc_distance, axis=1)
    df["azimuth_deg"] = df.apply(calc_azimuth, axis=1)

    return df


def full_match_pipeline(
    csv_path: Path,
    tx_path: Path,
    rx_lat: float,
    rx_lon: float,
    use_cache: bool = True
) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    """Run the full matching pipeline.

    Args:
        csv_path: Path to AbracaDABra CSV scan file
        tx_path: Path to TX database (dab-tx-list.csv)
        rx_lat: Receiver latitude
        rx_lon: Receiver longitude
        use_cache: Use cached data if available

    Returns:
        Tuple of (matched_df, processed_df, time_column)
        - matched_df: RX matched with TX data
        - processed_df: Deduplicated RX data
        - time_column: Name of the time column
    """
    # Parse CSV
    raw_df, processed_df, time_col = parse_csv(csv_path, use_cache=use_cache)

    # Load TX database
    tx_db = get_tx_database()
    tx_df = tx_db.load(tx_path)

    # Prepare RX for matching
    rx_for_match = prepare_rx_for_matching(raw_df)

    # Match
    matched = match_rx_tx(rx_for_match, tx_df)

    # Add distance
    if not matched.empty:
        matched = enrich_with_distance(matched, rx_lat, rx_lon)

    return matched, processed_df, time_col


def full_match_pipeline_multi(
    raw_df: pd.DataFrame,
    processed_df: pd.DataFrame,
    time_col: str | None,
    tx_path: Path,
    rx_lat: float,
    rx_lon: float,
) -> tuple[pd.DataFrame, pd.DataFrame, str | None]:
    """Run the full matching pipeline from pre-parsed DataFrames (multi-CSV).

    Args:
        raw_df: Combined raw DataFrame from all CSV files
        processed_df: Combined deduplicated DataFrame
        time_col: Name of the time column
        tx_path: Path to TX database (dab-tx-list.csv)
        rx_lat: Receiver latitude
        rx_lon: Receiver longitude

    Returns:
        Tuple of (matched_df, processed_df, time_column)
    """
    # Load TX database
    tx_db = get_tx_database()
    tx_df = tx_db.load(tx_path)

    # Prepare RX for matching
    rx_for_match = prepare_rx_for_matching(raw_df)

    # Match
    matched = match_rx_tx(rx_for_match, tx_df)

    # Add distance
    if not matched.empty:
        matched = enrich_with_distance(matched, rx_lat, rx_lon)

    return matched, processed_df, time_col
