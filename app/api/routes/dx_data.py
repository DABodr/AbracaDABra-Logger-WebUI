"""DX data API routes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ...config import get_config
from ...core.csv_parser import parse_all_abraca_csvs
from ...core.matcher import full_match_pipeline_multi
from ...core.aggregator import (
    aggregate_to_mux_groups,
    build_dx_table_response,
    build_dx_stats,
)
from ..models.dx import DXTableResponse, DXStatsResponse, MuxGroup, TIIDetail
from .status import update_status, clear_error

router = APIRouter(prefix="/api/dx", tags=["dx"])


def _get_mux_groups() -> tuple[list[MuxGroup], str | None]:
    """Get aggregated MuxGroups from current CSV data."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)
    tx_path = Path(config.paths.tx_db_path)

    try:
        # Parse all CSV files in directory
        raw_df, processed_df, time_col = parse_all_abraca_csvs(csv_dir)

        # Check if TX database exists
        if tx_path.exists():
            # Full matching pipeline with TX data
            matched_df, processed_df, time_col = full_match_pipeline_multi(
                raw_df=raw_df,
                processed_df=processed_df,
                time_col=time_col,
                tx_path=tx_path,
                rx_lat=config.rx.lat,
                rx_lon=config.rx.lon,
            )

            # Get TX database for EID filtering
            from ...core.tx_database import get_tx_database
            tx_db = get_tx_database()
            tx_df = tx_db.get_dataframe()

            mux_groups = aggregate_to_mux_groups(
                matched_df=matched_df,
                processed_df=processed_df,
                raw_df=raw_df,
                time_col=time_col,
                tx_df=tx_df,
            )
        else:
            # No TX database - parse CSV only
            from ...core.aggregator import _aggregate_without_tx
            mux_groups = _aggregate_without_tx(processed_df, raw_df, time_col)

        # Update status
        csv_name = f"{len(set(raw_df.get('_source_file', [])))} fichiers CSV" if '_source_file' in raw_df.columns else "all CSV"
        total_tii = sum(len(m.tii_list) for m in mux_groups)
        update_status(
            csv_file=csv_name,
            mux_count=len(mux_groups),
            tii_count=total_tii,
        )
        clear_error()

        return mux_groups, csv_name

    except Exception as e:
        update_status(error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/table", response_model=DXTableResponse)
async def get_dx_table(
    bloc: Optional[str] = Query(None, description="Filter by DAB bloc (e.g., 9A)")
) -> DXTableResponse:
    """Get DX table data with optional filtering."""
    mux_groups, csv_file = _get_mux_groups()

    # Apply filter if specified
    if bloc:
        bloc = bloc.strip().upper()
        mux_groups = [m for m in mux_groups if m.bloc == bloc]

    return build_dx_table_response(
        mux_groups=mux_groups,
        csv_file=csv_file,
        last_update=datetime.now(),
    )


@router.get("/tii/{bloc}/{ensemble}", response_model=list[TIIDetail])
async def get_tii_details(bloc: str, ensemble: str) -> list[TIIDetail]:
    """Get TII details for a specific mux."""
    mux_groups, _ = _get_mux_groups()

    bloc = bloc.strip().upper()
    ensemble = ensemble.strip()

    for mux in mux_groups:
        if mux.bloc == bloc and mux.ensemble == ensemble:
            return mux.tii_list

    raise HTTPException(
        status_code=404,
        detail=f"Mux not found: {bloc} / {ensemble}"
    )


@router.get("/stats", response_model=DXStatsResponse)
async def get_dx_stats() -> DXStatsResponse:
    """Get DX statistics."""
    mux_groups, _ = _get_mux_groups()
    return build_dx_stats(mux_groups)


@router.get("/blocs")
async def get_unique_blocs():
    """Get list of unique DAB blocs."""
    mux_groups, _ = _get_mux_groups()
    blocs = sorted(set(m.bloc for m in mux_groups))
    return {"blocs": blocs}


@router.post("/refresh")
async def refresh_data():
    """Force refresh of cached data."""
    from ...core.csv_parser import clear_cache

    clear_cache()

    try:
        mux_groups, csv_file = _get_mux_groups()
        return {
            "success": True,
            "mux_count": len(mux_groups),
            "csv_file": csv_file,
        }
    except HTTPException as e:
        return {"success": False, "error": e.detail}
