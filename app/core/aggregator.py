"""Data aggregation for WebUI display.

Groups data by ensemble/frequency and builds MuxGroup/TIIDetail models.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from ..api.models.dx import MuxGroup, TIIDetail, DXItem, DXTableResponse, DXStatsResponse
from ..api.models.map import RXMarker, TXMarker, ConnectionLine, MapMarkersResponse
from .csv_parser import get_frequency_mhz, channel_sort_key, get_services_count
from .tx_database import format_tii_code


def _get_latest_snr(raw_df: pd.DataFrame, bloc: str, ensemble: str, time_col: str | None) -> float | None:
    """Get SNR from the most recent scan for this ensemble.

    Returns None (to be displayed as 0 in red) if not in latest scan.
    """
    # Filter for this ensemble
    mask = (raw_df["Channel"] == bloc) & (raw_df["Label"] == ensemble)
    ensemble_rows = raw_df[mask]

    if ensemble_rows.empty:
        return None  # Not present → display as 0 (red)

    # If no time column, use first row
    if not time_col or time_col not in ensemble_rows.columns:
        snr = ensemble_rows.iloc[0].get("SNR [dB]")
        return float(snr) if pd.notna(snr) else None

    # Get most recent row by time
    ensemble_rows_sorted = ensemble_rows.sort_values(time_col, ascending=False, na_position="last")
    latest_row = ensemble_rows_sorted.iloc[0]

    snr = latest_row.get("SNR [dB]")
    return float(snr) if pd.notna(snr) else None


def aggregate_to_mux_groups(
    matched_df: pd.DataFrame,
    processed_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    time_col: str | None,
    tx_df: pd.DataFrame | None = None
) -> list[MuxGroup]:
    """Aggregate RX data into MuxGroup objects with smart TX matching.

    Logic (3 cases):
    1. Perfect match (block, eid, main, sub) in TX → Show with TX details
    2. EID unknown in TX (new multiplex) → Show without TX details (DX surprise!)
    3. EID known in TX BUT TII doesn't match → IGNORE (fake TII from AbracaDABra bug)

    Groups by (bloc, ensemble/label, eid) and collects TII details when available.
    """
    mux_groups: list[MuxGroup] = []

    # Get list of known EIDs from TX database (for Case 3 filtering)
    known_eids = set()
    if tx_df is not None and not tx_df.empty:
        known_eids = set(tx_df["eid"].dropna().unique())

    # Determine label column
    label_col = "Label" if "Label" in processed_df.columns else "ensemble_label"

    # Ensure EID column exists in processed_df
    if "eid" not in processed_df.columns:
        # If no EID, can't apply filtering logic → fallback to all
        processed_df_copy = processed_df.copy()
        processed_df_copy["eid"] = ""
    else:
        processed_df_copy = processed_df

    # Group all RX data by (Channel, Label, EID)
    grouped_rx = processed_df_copy.groupby(["Channel", label_col, "eid"], dropna=False)

    for (bloc, ensemble, eid), rx_group in grouped_rx:
        if not eid or pd.isna(eid):
            # No EID → skip (can't determine if valid)
            continue

        eid = str(eid)

        # Check if this ensemble has matched TX data
        if not matched_df.empty and "eid" in matched_df.columns:
            ensemble_matched = matched_df[
                (matched_df["eid"] == eid) & (matched_df["block"] == bloc)
            ]
        else:
            ensemble_matched = pd.DataFrame()

        # Case 1: Has TX matches → create MuxGroup with TX details
        if not ensemble_matched.empty:
            mux_group = _create_mux_group_with_tx(
                bloc, ensemble, eid, ensemble_matched, raw_df, time_col
            )
            mux_groups.append(mux_group)
        # Case 3: EID known in TX but no match → IGNORE (fake TII from bug)
        elif eid in known_eids:
            # Skip this ensemble (fake TII)
            continue
        # Case 2: EID unknown in TX → create MuxGroup without TX details (DX surprise!)
        else:
            mux_group = _create_mux_group_without_tx(
                bloc, ensemble, eid, rx_group, raw_df, time_col
            )
            mux_groups.append(mux_group)

    # Sort by channel
    mux_groups.sort(key=lambda m: channel_sort_key(m.bloc))

    return mux_groups


def _create_mux_group_with_tx(
    bloc: str,
    ensemble: str,
    eid: str,
    group: pd.DataFrame,
    raw_df: pd.DataFrame,
    time_col: str | None
) -> MuxGroup:
    """Create MuxGroup with TX details (Case 1: perfect match)."""
    freq_mhz = get_frequency_mhz(bloc)

    # Get time column for this group
    if time_col and time_col in group.columns:
        time_series = pd.to_datetime(group[time_col], errors="coerce")
        last_time = time_series.max() if not time_series.empty else None
    elif "rx_time" in group.columns:
        last_time = group["rx_time"].max()
    else:
        last_time = None

    # Build TII list
    tii_list: list[TIIDetail] = []
    seen_tii = set()

    for _, row in group.iterrows():
        main = int(row.get("main", 0))
        sub = int(row.get("sub", 0))
        tii_key = (main, sub)

        if tii_key in seen_tii:
            continue
        seen_tii.add(tii_key)

        tii_code = row.get("tii_code") or format_tii_code(main, sub)
        location = row.get("location", "")

        # Get SNR stats for this TII
        tii_mask = (group["main"] == main) & (group["sub"] == sub)
        tii_rows = group[tii_mask]

        snr_col = "SNR [dB]" if "SNR [dB]" in tii_rows.columns else "snr"
        snr_min_time = None
        snr_max_time = None
        if snr_col in tii_rows.columns:
            snr_vals = pd.to_numeric(tii_rows[snr_col], errors="coerce").dropna()
            snr_min = snr_vals.min() if not snr_vals.empty else None
            snr_max = snr_vals.max() if not snr_vals.empty else None
            if snr_min is not None and time_col and time_col in tii_rows.columns:
                min_idx = snr_vals.idxmin()
                snr_min_time = pd.to_datetime(tii_rows.loc[min_idx, time_col], errors="coerce")
                if pd.isna(snr_min_time):
                    snr_min_time = None
            if snr_max is not None and time_col and time_col in tii_rows.columns:
                max_idx = snr_vals.idxmax()
                snr_max_time = pd.to_datetime(tii_rows.loc[max_idx, time_col], errors="coerce")
                if pd.isna(snr_max_time):
                    snr_max_time = None
        else:
            snr_min = snr_max = None

        # Get level (relative power)
        level_col = "Level [dB]" if "Level [dB]" in tii_rows.columns else "level"
        if level_col in tii_rows.columns:
            level_vals = pd.to_numeric(tii_rows[level_col], errors="coerce").dropna()
            level_db = level_vals.mean() if not level_vals.empty else None
        else:
            level_db = None

        # Get last time for this TII
        if time_col and time_col in tii_rows.columns:
            tii_time = pd.to_datetime(tii_rows[time_col], errors="coerce").max()
        elif "rx_time" in tii_rows.columns:
            tii_time = tii_rows["rx_time"].max()
        else:
            tii_time = None

        # Determine if this TII is live (received less than 2 hours ago)
        is_live = False
        if pd.notna(tii_time):
            age_seconds = (pd.Timestamp.now() - tii_time).total_seconds()
            is_live = age_seconds < 7200  # 2h

        tii_detail = TIIDetail(
            tii_code=tii_code,
            main=main,
            sub=sub,
            location=str(location),
            lat=float(row.get("lat", 0)),
            lon=float(row.get("lon", 0)),
            distance_km=float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
            azimuth_deg=float(row.get("azimuth_deg")) if pd.notna(row.get("azimuth_deg")) else None,
            erp_kw=float(row.get("erp_kw")) if pd.notna(row.get("erp_kw")) else None,
            level_db=float(level_db) if level_db is not None else None,
            snr_min=float(snr_min) if snr_min is not None else None,
            snr_min_time=snr_min_time,
            snr_max=float(snr_max) if snr_max is not None else None,
            snr_max_time=snr_max_time,
            last_rx_time=tii_time if pd.notna(tii_time) else None,
            is_live=is_live,
        )
        tii_list.append(tii_detail)

    # Sort TII by level (reference site at 0.0 dB first, then by decreasing level)
    # Sites with no level_db go at the end
    # Use reverse=True because 0.0 > -5 > -10 (we want highest/least negative first)
    tii_list.sort(key=lambda t: (t.level_db is None, -(t.level_db if t.level_db is not None else -999)))

    # Get global SNR stats
    snr_col = "SNR [dB]" if "SNR [dB]" in group.columns else "snr"
    global_snr_min_time = None
    global_snr_max_time = None
    if snr_col in group.columns:
        snr_vals = pd.to_numeric(group[snr_col], errors="coerce").dropna()
        global_snr_min = snr_vals.min() if not snr_vals.empty else None
        global_snr_max = snr_vals.max() if not snr_vals.empty else None
        if global_snr_min is not None and time_col and time_col in group.columns:
            min_idx = snr_vals.idxmin()
            global_snr_min_time = pd.to_datetime(group.loc[min_idx, time_col], errors="coerce")
            if pd.isna(global_snr_min_time):
                global_snr_min_time = None
        if global_snr_max is not None and time_col and time_col in group.columns:
            max_idx = snr_vals.idxmax()
            global_snr_max_time = pd.to_datetime(group.loc[max_idx, time_col], errors="coerce")
            if pd.isna(global_snr_max_time):
                global_snr_max_time = None
    else:
        global_snr_min = global_snr_max = None

    # Get services count
    station_count = get_services_count(raw_df, bloc, ensemble)

    # Get latest SNR (from most recent scan)
    snr_live = _get_latest_snr(raw_df, bloc, ensemble, time_col)

    return MuxGroup(
        bloc=str(bloc),
        ensemble=str(ensemble),
        eid=str(eid),
        frequency_mhz=freq_mhz,
        tx_site_count=len(tii_list),
        station_count=station_count,
        tii_list=tii_list,
        snr_min=float(global_snr_min) if global_snr_min is not None else None,
        snr_min_time=global_snr_min_time,
        snr_max=float(global_snr_max) if global_snr_max is not None else None,
        snr_max_time=global_snr_max_time,
        snr_live=snr_live,
        last_rx_time=last_time if pd.notna(last_time) else None,
    )


def _create_mux_group_without_tx(
    bloc: str,
    ensemble: str,
    eid: str,
    group: pd.DataFrame,
    raw_df: pd.DataFrame,
    time_col: str | None
) -> MuxGroup:
    """Create MuxGroup without TX details (Case 2: unknown EID = DX surprise)."""
    freq_mhz = get_frequency_mhz(bloc)

    # Get time
    if time_col and time_col in group.columns:
        time_series = pd.to_datetime(group[time_col], errors="coerce")
        last_time = time_series.max() if not time_series.empty else None
    else:
        last_time = None

    # Get SNR stats from raw_df (all receptions for this ensemble)
    ensemble_mask = (raw_df["Channel"] == bloc) & (raw_df["Label"] == ensemble)
    ensemble_raw = raw_df[ensemble_mask]

    snr_min_time = None
    snr_max_time = None
    if not ensemble_raw.empty and "SNR [dB]" in ensemble_raw.columns:
        snr_vals = pd.to_numeric(ensemble_raw["SNR [dB]"], errors="coerce").dropna()
        snr_min = snr_vals.min() if not snr_vals.empty else None
        snr_max = snr_vals.max() if not snr_vals.empty else None
        if snr_min is not None and time_col and time_col in ensemble_raw.columns:
            min_idx = snr_vals.idxmin()
            snr_min_time = pd.to_datetime(ensemble_raw.loc[min_idx, time_col], errors="coerce")
            if pd.isna(snr_min_time):
                snr_min_time = None
        if snr_max is not None and time_col and time_col in ensemble_raw.columns:
            max_idx = snr_vals.idxmax()
            snr_max_time = pd.to_datetime(ensemble_raw.loc[max_idx, time_col], errors="coerce")
            if pd.isna(snr_max_time):
                snr_max_time = None
    else:
        snr_min = None
        snr_max = None

    station_count = get_services_count(raw_df, bloc, ensemble)

    # Get latest SNR (from most recent scan)
    snr_live = _get_latest_snr(raw_df, bloc, ensemble, time_col)

    # Extract TII information from raw_df even without TX match
    tii_list: list[TIIDetail] = []
    if not ensemble_raw.empty:
        # Check if Main/Sub columns exist
        has_main = "Main" in ensemble_raw.columns
        has_sub = "Sub" in ensemble_raw.columns

        if has_main and has_sub:
            # Extract unique TII codes (Main, Sub combinations)
            seen_tii = set()

            for _, row in ensemble_raw.iterrows():
                main_val = row.get("Main")
                sub_val = row.get("Sub")

                # Skip if Main or Sub is missing/invalid
                if pd.isna(main_val) or pd.isna(sub_val):
                    continue

                try:
                    main = int(main_val)
                    sub = int(sub_val)
                except (ValueError, TypeError):
                    continue

                tii_key = (main, sub)
                if tii_key in seen_tii:
                    continue
                seen_tii.add(tii_key)

                # Create TII code
                tii_code = format_tii_code(main, sub)

                # Get SNR stats for this specific TII
                tii_mask = (ensemble_raw["Main"] == main) & (ensemble_raw["Sub"] == sub)
                tii_rows = ensemble_raw[tii_mask]

                tii_snr_min_time = None
                tii_snr_max_time = None
                if not tii_rows.empty and "SNR [dB]" in tii_rows.columns:
                    tii_snr_vals = pd.to_numeric(tii_rows["SNR [dB]"], errors="coerce").dropna()
                    tii_snr_min = tii_snr_vals.min() if not tii_snr_vals.empty else None
                    tii_snr_max = tii_snr_vals.max() if not tii_snr_vals.empty else None
                    if tii_snr_min is not None and time_col and time_col in tii_rows.columns:
                        min_idx = tii_snr_vals.idxmin()
                        tii_snr_min_time = pd.to_datetime(tii_rows.loc[min_idx, time_col], errors="coerce")
                        if pd.isna(tii_snr_min_time):
                            tii_snr_min_time = None
                    if tii_snr_max is not None and time_col and time_col in tii_rows.columns:
                        max_idx = tii_snr_vals.idxmax()
                        tii_snr_max_time = pd.to_datetime(tii_rows.loc[max_idx, time_col], errors="coerce")
                        if pd.isna(tii_snr_max_time):
                            tii_snr_max_time = None
                else:
                    tii_snr_min = tii_snr_max = None

                # Get level (relative power)
                level_col = "Level [dB]"
                if level_col in tii_rows.columns:
                    level_vals = pd.to_numeric(tii_rows[level_col], errors="coerce").dropna()
                    level_db = level_vals.mean() if not level_vals.empty else None
                else:
                    level_db = None

                # Get last time for this TII
                if time_col and time_col in tii_rows.columns:
                    tii_time = pd.to_datetime(tii_rows[time_col], errors="coerce").max()
                else:
                    tii_time = None

                # Determine if this TII is live (received less than 2 hours ago)
                is_live = False
                if pd.notna(tii_time):
                    age_seconds = (pd.Timestamp.now() - tii_time).total_seconds()
                    is_live = age_seconds < 7200  # 2h

                # Create TII detail with "unknown" location
                tii_detail = TIIDetail(
                    tii_code=tii_code,
                    main=main,
                    sub=sub,
                    location=f"TII {tii_code} - Non disponible dans la base de données",
                    lat=0.0,
                    lon=0.0,
                    distance_km=0.0,
                    azimuth_deg=None,
                    erp_kw=None,
                    level_db=float(level_db) if level_db is not None else None,
                    snr_min=float(tii_snr_min) if tii_snr_min is not None else None,
                    snr_min_time=tii_snr_min_time,
                    snr_max=float(tii_snr_max) if tii_snr_max is not None else None,
                    snr_max_time=tii_snr_max_time,
                    last_rx_time=tii_time if pd.notna(tii_time) else None,
                    is_live=is_live,
                )
                tii_list.append(tii_detail)

            # Sort TII by level (if available), then by TII code
            tii_list.sort(key=lambda t: (t.level_db is None, -(t.level_db if t.level_db is not None else -999)))

    return MuxGroup(
        bloc=str(bloc),
        ensemble=str(ensemble),
        eid=eid,
        frequency_mhz=freq_mhz,
        tx_site_count=len(tii_list),
        station_count=station_count,
        tii_list=tii_list,
        snr_min=float(snr_min) if pd.notna(snr_min) else None,
        snr_min_time=snr_min_time,
        snr_max=float(snr_max) if pd.notna(snr_max) else None,
        snr_max_time=snr_max_time,
        snr_live=snr_live,
        last_rx_time=last_time if pd.notna(last_time) else None,
    )

    for (bloc, ensemble, eid), group in grouped:
        # Get frequency
        freq_mhz = get_frequency_mhz(bloc)

        # Get time column for this group
        if time_col and time_col in group.columns:
            time_series = pd.to_datetime(group[time_col], errors="coerce")
            last_time = time_series.max() if not time_series.empty else None
        elif "rx_time" in group.columns:
            last_time = group["rx_time"].max()
        else:
            last_time = None

        # Build TII list
        tii_list: list[TIIDetail] = []
        seen_tii = set()

        for _, row in group.iterrows():
            main = int(row.get("main", 0))
            sub = int(row.get("sub", 0))
            tii_key = (main, sub)

            if tii_key in seen_tii:
                continue
            seen_tii.add(tii_key)

            tii_code = row.get("tii_code") or format_tii_code(main, sub)
            location = row.get("location", "")

            # Get SNR stats for this TII
            tii_mask = (group["main"] == main) & (group["sub"] == sub)
            tii_rows = group[tii_mask]

            snr_col = "SNR [dB]" if "SNR [dB]" in tii_rows.columns else "snr"
            if snr_col in tii_rows.columns:
                snr_vals = pd.to_numeric(tii_rows[snr_col], errors="coerce").dropna()
                snr_min = snr_vals.min() if not snr_vals.empty else None
                snr_max = snr_vals.max() if not snr_vals.empty else None
            else:
                snr_min = snr_max = None

            # Get last time for this TII
            if time_col and time_col in tii_rows.columns:
                tii_time = pd.to_datetime(tii_rows[time_col], errors="coerce").max()
            elif "rx_time" in tii_rows.columns:
                tii_time = tii_rows["rx_time"].max()
            else:
                tii_time = None

            tii_detail = TIIDetail(
                tii_code=tii_code,
                main=main,
                sub=sub,
                location=str(location),
                lat=float(row.get("lat", 0)),
                lon=float(row.get("lon", 0)),
                distance_km=float(row.get("distance_km", 0)) if pd.notna(row.get("distance_km")) else 0,
                azimuth_deg=float(row.get("azimuth_deg")) if pd.notna(row.get("azimuth_deg")) else None,
                erp_kw=float(row.get("erp_kw")) if pd.notna(row.get("erp_kw")) else None,
                snr_min=float(snr_min) if snr_min is not None else None,
                snr_max=float(snr_max) if snr_max is not None else None,
                last_rx_time=tii_time if pd.notna(tii_time) else None,
            )
            tii_list.append(tii_detail)

        # Sort TII by distance
        tii_list.sort(key=lambda t: t.distance_km)

        # Get global SNR stats
        snr_col = "SNR [dB]" if "SNR [dB]" in group.columns else "snr"
        if snr_col in group.columns:
            snr_vals = pd.to_numeric(group[snr_col], errors="coerce").dropna()
            global_snr_min = snr_vals.min() if not snr_vals.empty else None
            global_snr_max = snr_vals.max() if not snr_vals.empty else None
        else:
            global_snr_min = global_snr_max = None

        # Get services count
        station_count = get_services_count(raw_df, bloc, ensemble)

        mux_group = MuxGroup(
            bloc=str(bloc),
            ensemble=str(ensemble),
            eid=str(eid),
            frequency_mhz=freq_mhz,
            tx_site_count=len(tii_list),
            station_count=station_count,
            tii_list=tii_list,
            snr_min=float(global_snr_min) if global_snr_min is not None else None,
            snr_max=float(global_snr_max) if global_snr_max is not None else None,
            last_rx_time=last_time if pd.notna(last_time) else None,
        )
        mux_groups.append(mux_group)

    # Sort by channel
    mux_groups.sort(key=lambda m: channel_sort_key(m.bloc))

    return mux_groups


def _aggregate_without_tx(
    processed_df: pd.DataFrame,
    raw_df: pd.DataFrame,
    time_col: str | None
) -> list[MuxGroup]:
    """Create MuxGroups without TX matching (no TII details)."""
    mux_groups: list[MuxGroup] = []

    if processed_df.empty:
        return mux_groups

    grouped = processed_df.groupby(["Channel", "Label"], dropna=False)

    for (bloc, ensemble), group in grouped:
        freq_mhz = get_frequency_mhz(bloc)

        # Get EID if available
        eid = ""
        if "eid" in group.columns:
            eids = group["eid"].dropna().unique()
            if len(eids) > 0:
                eid = str(eids[0])

        # Get time
        if time_col and time_col in group.columns:
            time_series = pd.to_datetime(group[time_col], errors="coerce")
            last_time = time_series.max() if not time_series.empty else None
        else:
            last_time = None

        # Get SNR stats
        if "SNR_max" in group.columns:
            snr_max = group["SNR_max"].max()
        elif "SNR [dB]" in group.columns:
            snr_max = group["SNR [dB]"].max()
        else:
            snr_max = None

        if "SNR_min" in group.columns:
            snr_min = group["SNR_min"].min()
        elif "SNR [dB]" in group.columns:
            snr_min = group["SNR [dB]"].min()
        else:
            snr_min = None

        station_count = get_services_count(raw_df, bloc, ensemble)

        # Get latest SNR (from most recent scan)
        snr_live = _get_latest_snr(raw_df, bloc, ensemble, time_col)

        mux_group = MuxGroup(
            bloc=str(bloc),
            ensemble=str(ensemble),
            eid=eid,
            frequency_mhz=freq_mhz,
            tx_site_count=0,
            station_count=station_count,
            tii_list=[],
            snr_min=float(snr_min) if pd.notna(snr_min) else None,
            snr_max=float(snr_max) if pd.notna(snr_max) else None,
            snr_live=snr_live,
            last_rx_time=last_time if pd.notna(last_time) else None,
        )
        mux_groups.append(mux_group)

    mux_groups.sort(key=lambda m: channel_sort_key(m.bloc))
    return mux_groups


def build_dx_table_response(
    mux_groups: list[MuxGroup],
    csv_file: str | None = None,
    last_update: datetime | None = None
) -> DXTableResponse:
    """Build DXTableResponse from MuxGroups."""
    total_tii = sum(len(m.tii_list) for m in mux_groups)

    return DXTableResponse(
        mux_groups=mux_groups,
        total_mux=len(mux_groups),
        total_tii=total_tii,
        last_update=last_update,
        csv_file=csv_file,
    )


def build_dx_stats(mux_groups: list[MuxGroup]) -> DXStatsResponse:
    """Build statistics from MuxGroups."""
    total_tii = 0
    unique_locations = set()
    furthest_km = 0.0
    best_snr = None

    for mux in mux_groups:
        total_tii += len(mux.tii_list)
        for tii in mux.tii_list:
            if tii.location:
                unique_locations.add(tii.location)
            if tii.distance_km > furthest_km:
                furthest_km = tii.distance_km
            if tii.snr_max is not None:
                if best_snr is None or tii.snr_max > best_snr:
                    best_snr = tii.snr_max

    unique_blocs = len(set(m.bloc for m in mux_groups))

    return DXStatsResponse(
        total_mux=len(mux_groups),
        total_tii=total_tii,
        unique_blocs=unique_blocs,
        unique_locations=len(unique_locations),
        furthest_km=furthest_km if furthest_km > 0 else None,
        best_snr=best_snr,
    )


def build_map_markers(
    mux_groups: list[MuxGroup],
    rx_name: str,
    rx_lat: float,
    rx_lon: float
) -> MapMarkersResponse:
    """Build map markers from MuxGroups."""
    from app.api.models.map import TXEnsemble

    rx_marker = RXMarker(name=rx_name, lat=rx_lat, lon=rx_lon)

    # Group all ensembles by location (lat, lon)
    sites_dict: dict[tuple[float, float], dict] = {}

    for mux in mux_groups:
        for tii in mux.tii_list:
            # Skip TII without valid location (not in database)
            if tii.lat == 0.0 and tii.lon == 0.0:
                continue

            loc_key = (tii.lat, tii.lon)

            # Initialize site if not seen before
            if loc_key not in sites_dict:
                sites_dict[loc_key] = {
                    'location': tii.location,
                    'lat': tii.lat,
                    'lon': tii.lon,
                    'distance_km': tii.distance_km,
                    'azimuth_deg': tii.azimuth_deg,
                    'erp_kw': tii.erp_kw,
                    'ensembles': []
                }

            # Add ensemble to this site
            ensemble = TXEnsemble(
                bloc=mux.bloc,
                ensemble=mux.ensemble,
                eid=mux.eid,
                tii_code=tii.tii_code,
                main=tii.main,
                sub=tii.sub,
                snr_min=tii.snr_min,
                snr_min_time=tii.snr_min_time,
                snr_max=tii.snr_max,
                snr_max_time=tii.snr_max_time,
                level_db=tii.level_db,
                is_live=tii.is_live,
                last_rx_time=tii.last_rx_time,
            )
            sites_dict[loc_key]['ensembles'].append(ensemble)

    # Create TX markers and lines
    tx_markers: list[TXMarker] = []
    lines: list[ConnectionLine] = []

    for loc_key, site_data in sites_dict.items():
        tx_marker = TXMarker(
            location=site_data['location'],
            lat=site_data['lat'],
            lon=site_data['lon'],
            distance_km=site_data['distance_km'],
            azimuth_deg=site_data['azimuth_deg'],
            erp_kw=site_data['erp_kw'],
            ensembles=site_data['ensembles'],
        )
        tx_markers.append(tx_marker)

        # Use the first ensemble's TII code for the line
        first_tii_code = site_data['ensembles'][0].tii_code if site_data['ensembles'] else "?"
        line = ConnectionLine(
            from_lat=rx_lat,
            from_lon=rx_lon,
            to_lat=site_data['lat'],
            to_lon=site_data['lon'],
            tii_code=first_tii_code,
            distance_km=site_data['distance_km'],
        )
        lines.append(line)

    # Sort TX markers by distance
    tx_markers.sort(key=lambda m: m.distance_km)

    return MapMarkersResponse(
        rx=rx_marker,
        tx_markers=tx_markers,
        lines=lines,
        center_lat=rx_lat,
        center_lon=rx_lon,
        zoom=6,
    )
