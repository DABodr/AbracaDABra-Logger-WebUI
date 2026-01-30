"""Pydantic models for map data."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class RXMarker(BaseModel):
    """Receiver marker on map."""
    name: str
    lat: float
    lon: float
    marker_type: str = "rx"


class TXMarker(BaseModel):
    """Transmitter marker on map."""
    tii_code: str
    location: str
    lat: float
    lon: float
    distance_km: float
    azimuth_deg: Optional[float] = None
    bloc: str
    ensemble: str
    eid: str
    snr_min: Optional[float] = None
    snr_max: Optional[float] = None
    erp_kw: Optional[float] = None
    marker_type: str = "tx"


class ConnectionLine(BaseModel):
    """Line connecting RX to TX."""
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    tii_code: str
    distance_km: float


class MapMarkersResponse(BaseModel):
    """Response containing all map markers."""
    rx: RXMarker
    tx_markers: list[TXMarker] = Field(default_factory=list)
    lines: list[ConnectionLine] = Field(default_factory=list)
    center_lat: float
    center_lon: float
    zoom: int = 6


class MapConfigResponse(BaseModel):
    """Map configuration response."""
    center_lat: float
    center_lon: float
    zoom: int = 6
    tile_url: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    attribution: str = "&copy; OpenStreetMap contributors"
