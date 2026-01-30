"""Telegram bot integration.

Refactored from abracadabra_dx_bot.py
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from ..config import get_config
from .csv_parser import choose_latest_abraca_csv, parse_csv, is_dab_block, channel_sort_key

# Bot state
_bot_thread: Optional[threading.Thread] = None
_bot_running = False
_last_update_id = 0
_stats = {
    "messages_processed": 0,
    "last_command": None,
    "last_command_time": None,
    "errors": 0,
}


def is_bot_running() -> bool:
    """Check if bot is running."""
    return _bot_running and _bot_thread is not None and _bot_thread.is_alive()


def get_bot_stats() -> dict:
    """Get bot statistics."""
    return _stats.copy()


def start_telegram_bot() -> None:
    """Start the Telegram bot in a background thread."""
    global _bot_thread, _bot_running

    if is_bot_running():
        return

    _bot_running = True
    _bot_thread = threading.Thread(target=_bot_loop, daemon=True)
    _bot_thread.start()


def stop_telegram_bot() -> None:
    """Stop the Telegram bot."""
    global _bot_running
    _bot_running = False


def _bot_loop() -> None:
    """Main bot polling loop."""
    global _bot_running

    config = get_config()

    while _bot_running:
        try:
            _poll_telegram()
        except Exception as e:
            _stats["errors"] += 1
            print(f"Telegram bot error: {e}")

        time.sleep(config.telegram.poll_interval_sec)


def _allowed_chat(chat_id: int) -> bool:
    """Check if chat is allowed."""
    config = get_config()
    allowed_raw = config.telegram.allowed_chats.strip()

    if not allowed_raw:
        return True

    allowed = {x.strip() for x in allowed_raw.split(",") if x.strip()}
    return str(chat_id) in allowed


def _tg_send(chat_id: int, text: str) -> None:
    """Send a message to Telegram."""
    config = get_config()
    token = config.telegram.token

    if not token:
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(
            url,
            data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception:
        pass


def _poll_telegram() -> None:
    """Poll for Telegram updates."""
    global _last_update_id

    config = get_config()
    token = config.telegram.token

    if not token:
        return

    try:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        data = requests.get(
            url,
            params={"offset": _last_update_id + 1, "timeout": 0},
            timeout=10,
        ).json()

        if not data.get("ok"):
            return

        for upd in data.get("result", []):
            _last_update_id = max(_last_update_id, upd.get("update_id", 0))

            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue

            chat_id = int(msg.get("chat", {}).get("id", 0))
            if not _allowed_chat(chat_id):
                continue

            text = (msg.get("text") or "").strip()
            if not text:
                continue

            _handle_message(chat_id, text)

    except Exception:
        _stats["errors"] += 1


def _handle_message(chat_id: int, text: str) -> None:
    """Handle incoming message."""
    _stats["messages_processed"] += 1
    _stats["last_command"] = text[:50]
    _stats["last_command_time"] = datetime.now().isoformat()

    norm = text.lower().strip()
    upper = text.upper().strip()
    tokens = upper.split()

    if norm in {"help", "/help"}:
        _send_help(chat_id)
        return

    if norm in {"status", "/status"}:
        _send_status(chat_id)
        return

    if norm.startswith("last") or norm.startswith("/last"):
        _send_last(chat_id, text)
        return

    if norm.startswith("dx") or norm.startswith("/dx"):
        _send_dx(chat_id, text)
        return

    if tokens and is_dab_block(tokens[0]):
        _send_dx(chat_id, "DX " + text)
        return

    if tokens and re.match(r"^[<>]\s*\d+(\.\d+)?$", tokens[0].replace(" ", "")):
        _send_dx(chat_id, "DX " + text)
        return

    if tokens and tokens[0] == "LOCAL":
        _send_dx(chat_id, "DX LOCAL")
        return


def _send_help(chat_id: int) -> None:
    """Send help message."""
    msg = (
        "*AbracaDABra DX Bot*\n\n"
        "Commands:\n"
        "`DX` - all mux (latest snapshot)\n"
        "`DX 10` - limit to 10\n"
        "`DX 9B` - filter by block\n"
        "`9B` - shortcut for `DX 9B`\n"
        "`DX >300` - distance filter (>300km)\n"
        "`>300` / `<50` - shortcuts\n"
        "`LOCAL` - shortcut for `<50`\n"
        "`LAST` / `LAST 5` - most recent mux\n"
        "`STATUS` - script status\n"
        "`HELP` - this memo\n"
    )
    _tg_send(chat_id, msg)


def _send_status(chat_id: int) -> None:
    """Send status message."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)

    csv_file = choose_latest_abraca_csv(csv_dir)
    csv_name = csv_file.name if csv_file else "—"

    msg = (
        "*STATUS*\n"
        f"CSV Dir: `{csv_dir}`\n"
        f"Latest CSV: `{csv_name}`\n"
        f"RX: `{config.rx.name}`\n"
        f"Lat/Lon: `{config.rx.lat}, {config.rx.lon}`\n"
    )
    _tg_send(chat_id, msg)


def _get_dx_snapshot() -> list[dict]:
    """Get current DX snapshot."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)

    csv_file = choose_latest_abraca_csv(csv_dir)
    if not csv_file:
        return []

    try:
        raw_df, processed_df, time_col = parse_csv(csv_file, use_cache=True)

        items = []
        for _, row in processed_df.iterrows():
            t_str = str(row.get(time_col, "")).strip() if time_col else ""

            dist_val = row.get("Distance [km]")
            snr_val = row.get("SNR_max")

            items.append({
                "channel": str(row.get("Channel", "")).strip().upper(),
                "label": str(row.get("Label", "")).strip(),
                "location": str(row.get("Location", "")).strip(),
                "distance": float(dist_val) if pd.notna(dist_val) else None,
                "snr_max": float(snr_val) if pd.notna(snr_val) else None,
                "time": t_str,
            })

        # Sort by distance descending
        items.sort(key=lambda x: (x["distance"] is not None, x["distance"] or 0), reverse=True)
        return items

    except Exception:
        return []


def _send_dx(chat_id: int, text: str) -> None:
    """Send DX response."""
    import pandas as pd

    items = _get_dx_snapshot()
    if not items:
        _tg_send(chat_id, "No DX data available.")
        return

    # Parse command
    channel, min_dist, max_dist, limit = _parse_dx_command(text)

    # Apply filters
    if channel:
        items = [it for it in items if it["channel"] == channel]

    if min_dist is not None:
        items = [it for it in items if it["distance"] is not None and it["distance"] > min_dist]

    if max_dist is not None:
        items = [it for it in items if it["distance"] is not None and it["distance"] < max_dist]

    if limit is not None and limit > 0:
        items = items[:limit]

    # Format response
    now = datetime.now().strftime("%d/%m %H:%M")
    n = len(items)

    if channel:
        mux_label = items[0].get("label", "") if items else ""
        header = f"*DX {channel}* — {mux_label} — {now} ({n})"
    else:
        header = f"*DX* — {now} ({n})"

    if not items:
        _tg_send(chat_id, header + "\nNo results.")
        return

    lines = []
    for it in items[:50]:
        dist = it["distance"]
        snr = it["snr_max"]

        dist_badge = _get_distance_badge(dist)
        snr_badge = _get_snr_badge(snr)

        dist_txt = f"{dist:5.1f}km" if dist is not None else "  ?km"
        snr_txt = f"{snr:4.1f}dB{snr_badge}" if snr is not None else f"  ?dB{snr_badge}"

        loc = it.get("location", "")[:30]
        lines.append(f"{dist_badge} {dist_txt:>8}  {snr_txt:>8}  {loc}")

    _tg_send(chat_id, header + "\n```\n" + "\n".join(lines) + "\n```")


def _send_last(chat_id: int, text: str) -> None:
    """Send LAST response."""
    items = _get_dx_snapshot()
    if not items:
        _tg_send(chat_id, "No DX data available.")
        return

    # Parse limit
    parts = text.strip().split()
    n = 1
    if len(parts) >= 2 and parts[1].isdigit():
        n = max(1, min(20, int(parts[1])))

    # Sort by time (assuming most recent first in snapshot)
    items = items[:n]

    now = datetime.now().strftime("%d/%m %H:%M")
    header = f"*LAST* — {now} ({len(items)})"

    lines = []
    for it in items:
        ch = it.get("channel", "?")
        dist = it.get("distance")
        snr = it.get("snr_max")

        db = _get_distance_badge(dist)
        sb = _get_snr_badge(snr)

        dist_txt = f"{dist:5.1f}km" if dist is not None else "  ?km"
        snr_txt = f"{snr:4.1f}dB{sb}" if snr is not None else f"  ?dB{sb}"

        label = it.get("label", "")[:18]
        lines.append(f"{db} {ch:>2}  {dist_txt:>8}  {snr_txt:>8}  {label}")

    _tg_send(chat_id, header + "\n```\n" + "\n".join(lines) + "\n```")


def _parse_dx_command(text: str) -> tuple[str | None, float | None, float | None, int | None]:
    """Parse DX command arguments."""
    parts = text.strip().split()
    channel = None
    min_dist = None
    max_dist = None
    limit = None

    for tok in parts[1:]:
        t_raw = tok.strip()
        t = t_raw.upper()

        if t == "LOCAL":
            max_dist = 50.0
            continue

        m = re.match(r"^>\s*(\d+(\.\d+)?)$", t_raw.replace(" ", ""))
        if m:
            min_dist = float(m.group(1))
            continue

        m = re.match(r"^<\s*(\d+(\.\d+)?)$", t_raw.replace(" ", ""))
        if m:
            max_dist = float(m.group(1))
            continue

        if t.isdigit():
            limit = int(t)
            continue

        if is_dab_block(t):
            channel = t
            continue

    return channel, min_dist, max_dist, limit


def _get_distance_badge(dist) -> str:
    """Get emoji badge for distance."""
    try:
        d = float(dist)
        if d > 300:
            return "[P]"  # Purple equivalent
        elif d > 100:
            return "[O]"  # Orange equivalent
        else:
            return "[G]"  # Green equivalent
    except Exception:
        return "[ ]"


def _get_snr_badge(snr) -> str:
    """Get emoji badge for SNR."""
    try:
        v = float(snr)
        if v < 6:
            return "[!]"  # Red equivalent
        elif v < 10:
            return "[~]"  # Orange equivalent
        else:
            return "[+]"  # Green equivalent
    except Exception:
        return "[ ]"
