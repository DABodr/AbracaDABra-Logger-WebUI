"""Map data API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...config import get_config
from ...core.csv_parser import choose_latest_abraca_csv, parse_csv
from ...core.matcher import full_match_pipeline
from ...core.aggregator import aggregate_to_mux_groups, build_map_markers
from ..models.map import MapMarkersResponse, MapConfigResponse

router = APIRouter(prefix="/api/map", tags=["map"])


@router.get("/markers", response_model=MapMarkersResponse)
async def get_map_markers() -> MapMarkersResponse:
    """Get all map markers (RX and TX)."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)
    tx_path = Path(config.paths.tx_db_path)

    # Find latest CSV
    csv_file = choose_latest_abraca_csv(csv_dir)
    if csv_file is None:
        # Return empty map with just RX marker
        from ..models.map import RXMarker
        return MapMarkersResponse(
            rx=RXMarker(name=config.rx.name, lat=config.rx.lat, lon=config.rx.lon),
            tx_markers=[],
            lines=[],
            center_lat=config.rx.lat,
            center_lon=config.rx.lon,
            zoom=6,
        )

    try:
        if tx_path.exists():
            # Full matching pipeline
            matched_df, processed_df, time_col = full_match_pipeline(
                csv_path=csv_file,
                tx_path=tx_path,
                rx_lat=config.rx.lat,
                rx_lon=config.rx.lon,
                use_cache=True,
            )

            raw_df, _, _ = parse_csv(csv_file, use_cache=True)

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
            # No TX database - empty markers
            mux_groups = []

        return build_map_markers(
            mux_groups=mux_groups,
            rx_name=config.rx.name,
            rx_lat=config.rx.lat,
            rx_lon=config.rx.lon,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config", response_model=MapConfigResponse)
async def get_map_config() -> MapConfigResponse:
    """Get map configuration."""
    config = get_config()

    return MapConfigResponse(
        center_lat=config.rx.lat,
        center_lon=config.rx.lon,
        zoom=6,
        tile_url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution="&copy; OpenStreetMap contributors",
    )
