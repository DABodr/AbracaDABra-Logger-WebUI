"""Pydantic models for DX data."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TIIDetail(BaseModel):
    """Details for a single TII transmitter site."""
    tii_code: str = Field(..., description="TII code (e.g., '24A1', '0801')")
    main: int = Field(..., description="Main ID")
    sub: int = Field(..., description="Sub ID")
    location: str = Field(..., description="Transmitter location name")
    lat: float = Field(..., description="Latitude")
    lon: float = Field(..., description="Longitude")
    distance_km: float = Field(..., description="Distance from RX in km")
    azimuth_deg: Optional[float] = Field(None, description="Azimuth from RX in degrees")
    erp_kw: Optional[float] = Field(None, description="Effective radiated power in kW")
    level_db: Optional[float] = Field(None, description="Relative power level in dB (0.0 = reference)")
    snr_min: Optional[float] = Field(None, description="Minimum SNR recorded")
    snr_min_time: Optional[datetime] = Field(None, description="Time when SNR min was recorded")
    snr_max: Optional[float] = Field(None, description="Maximum SNR recorded")
    snr_max_time: Optional[datetime] = Field(None, description="Time when SNR max was recorded")
    last_rx_time: Optional[datetime] = Field(None, description="Last reception time")
    is_live: bool = Field(False, description="True if present in latest scan")


class MuxGroup(BaseModel):
    """Aggregated data for a mux (ensemble) grouped by bloc and frequency."""
    bloc: str = Field(..., description="DAB block (e.g., '5C', '9A')")
    ensemble: str = Field(..., description="Ensemble/Mux label")
    eid: str = Field(..., description="Ensemble ID (4 hex digits)")
    frequency_mhz: float = Field(..., description="Frequency in MHz")
    tx_site_count: int = Field(..., description="Number of unique TX sites")
    station_count: int = Field(0, description="Number of services/stations")
    tii_list: list[TIIDetail] = Field(default_factory=list, description="List of TII transmitters")
    snr_min: Optional[float] = Field(None, description="Global minimum SNR ever recorded")
    snr_min_time: Optional[datetime] = Field(None, description="Time when SNR min was recorded")
    snr_max: Optional[float] = Field(None, description="Global maximum SNR ever recorded")
    snr_max_time: Optional[datetime] = Field(None, description="Time when SNR max was recorded")
    snr_live: Optional[float] = Field(None, description="Current SNR from latest scan (0 = not present)")
    last_rx_time: Optional[datetime] = Field(None, description="Most recent reception time")


class DXItem(BaseModel):
    """Raw DX item from scan."""
    channel: str
    label: str
    location: str
    distance_km: Optional[float] = None
    snr: Optional[float] = None
    snr_min: Optional[float] = None
    snr_max: Optional[float] = None
    time_str: str = ""
    time_dt: Optional[datetime] = None
    main: Optional[int] = None
    sub: Optional[int] = None
    tii_code: Optional[str] = None


class DXTableResponse(BaseModel):
    """Response for the DX table endpoint."""
    mux_groups: list[MuxGroup]
    total_mux: int
    total_tii: int
    last_update: Optional[datetime] = None
    csv_file: Optional[str] = None


class DXStatsResponse(BaseModel):
    """Summary statistics."""
    total_mux: int
    total_tii: int
    unique_blocs: int
    unique_locations: int
    furthest_km: Optional[float] = None
    best_snr: Optional[float] = None
