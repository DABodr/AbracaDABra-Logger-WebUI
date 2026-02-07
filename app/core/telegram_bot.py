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
from .csv_parser import choose_latest_abraca_csv, parse_csv, parse_all_abraca_csvs, is_dab_block, channel_sort_key

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


def send_test_message(token: str, chat_id: str) -> bool:
    """Send a test message to verify bot configuration."""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            data={
                "chat_id": chat_id,
                "text": "AbracaDABra Logger WebUI - Test OK",
                "parse_mode": "Markdown",
            },
            timeout=10,
        )
        return resp.status_code == 200 and resp.json().get("ok", False)
    except Exception:
        return False


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


def _cut(s: str, n: int) -> str:
    """Truncate string with ellipsis."""
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def _hhmm(t: str) -> str:
    """Extract HH:MM from time string."""
    t = t or ""
    return t.split("-")[-1].strip() if "-" in t else t[-5:]


def _send_help(chat_id: int) -> None:
    """Send help message."""
    msg = (
        "\U0001F916 *AbracaDABra DX Bot*\n\n"
        "Commands:\n"
        "`DX` \u2192 all mux (latest snapshot)\n"
        "`DX 10` \u2192 limit 10\n"
        "`DX 9B` \u2192 filter by block\n"
        "`9B` \u2192 shortcut for `DX 9B`\n"
        "`DX >300` \u2192 distance filter\n"
        "`>300` / `<50` \u2192 shortcuts\n"
        "`LOCAL` \u2192 shortcut for `<50`\n"
        "`LAST` / `LAST 5` \u2192 most recent mux\n"
        "`STATUS` \u2192 script status\n"
        "`HELP` \u2192 this memo\n"
    )
    _tg_send(chat_id, msg)


def _send_status(chat_id: int) -> None:
    """Send status message."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)

    csv_file = choose_latest_abraca_csv(csv_dir)
    csv_name = csv_file.name if csv_file else "\u2014"

    msg = (
        "\U0001F7E2 *STATUS*\n"
        f"CSV Dir: `{csv_dir}`\n"
        f"Latest CSV: `{csv_name}`\n"
        f"RX: `{config.rx.name}`\n"
        f"Lat/Lon: `{config.rx.lat}, {config.rx.lon}`\n"
    )
    _tg_send(chat_id, msg)


def _get_dx_snapshot() -> list[dict]:
    """Get current DX snapshot from all recent CSV files."""
    config = get_config()
    csv_dir = Path(config.paths.csv_dir)

    try:
        raw_df, processed_df, time_col = parse_all_abraca_csvs(csv_dir)

        items = []
        for _, row in processed_df.iterrows():
            t_str = str(row.get(time_col, "")).strip() if time_col else ""

            loc = str(row.get("Location", "")).strip()
            if not loc or loc.lower() == "nan":
                continue

            dist_val = row.get("Distance [km]")
            snr_val = row.get("SNR_max")

            items.append({
                "channel": str(row.get("Channel", "")).strip().upper(),
                "label": str(row.get("Label", "")).strip(),
                "location": loc,
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
    items = _get_dx_snapshot()
    if not items:
        _tg_send(chat_id, "\u2139\uFE0F No DX snapshot yet.")
        return

    # Parse command
    channel, min_dist, max_dist, limit = _parse_dx_command(text)

    # Build filter description
    filter_bits = []

    # Apply filters
    if channel:
        items = [it for it in items if it["channel"] == channel]

    if min_dist is not None:
        items = [it for it in items if it["distance"] is not None and it["distance"] > min_dist]
        filter_bits.append(f">{min_dist:g}km")

    if max_dist is not None:
        items = [it for it in items if it["distance"] is not None and it["distance"] < max_dist]
        filter_bits.append(f"<{max_dist:g}km")

    if limit is not None and limit > 0:
        items = items[:limit]

    # Format response
    now = datetime.now().strftime("%d/%m %H:%M")
    n = len(items)

    if channel:
        mux_label = _cut(items[0].get("label", ""), 22) if items else ""
        header = f"\U0001F4E1 DX {channel} \u2014 {mux_label} \u2014 {now} ({n})"
    else:
        header = f"\U0001F4E1 DX \u2014 {now} ({n})"
        if filter_bits:
            header += f"\nFilter: {' | '.join(filter_bits)}"

    if not items:
        _tg_send(chat_id, header + "\nNo results.")
        return

    lines = []

    if channel:
        # Single channel: flat list
        for it in items[:55]:
            dist = it["distance"]
            snr = it["snr_max"]

            dist_badge = _get_distance_badge(dist)
            snr_badge = _get_snr_badge(snr)

            dist_txt = f"{dist:5.1f}km" if dist is not None else "  ?km"
            snr_txt = f"{snr:4.1f}dB{snr_badge}" if snr is not None else f"  ?dB{snr_badge}"

            lines.append(f"{dist_badge} {dist_txt:>8}  {snr_txt:>8}  {_hhmm(it.get('time', '')):>5}  {_cut(it.get('location', ''), 34)}")

        _tg_send(chat_id, header + "\n```text\n" + "\n".join(lines) + "\n```")
    else:
        # All channels: group by block
        groups = {}
        for it in items:
            ch = (it.get("channel") or "?").strip().upper()
            groups.setdefault(ch, []).append(it)

        for ch in sorted(groups.keys(), key=channel_sort_key):
            lines.append(ch)
            block_items = sorted(groups[ch], key=lambda x: (x["distance"] is not None, x["distance"] or 0), reverse=True)
            for it in block_items[:30]:
                dist = it["distance"]
                snr = it["snr_max"]

                dist_badge = _get_distance_badge(dist)
                snr_badge = _get_snr_badge(snr)

                dist_txt = f"{dist:5.1f}km" if dist is not None else "  ?km"
                snr_txt = f"{snr:4.1f}dB{snr_badge}" if snr is not None else f"  ?dB{snr_badge}"

                lines.append(f"  {dist_badge} {dist_txt:>8}  {snr_txt:>8}  {_hhmm(it.get('time', '')):>5}  {_cut(it.get('location', ''), 30)}")
            lines.append("")

        _tg_send(chat_id, header + "\n```text\n" + "\n".join(lines[:80]).rstrip() + "\n```")


def _send_last(chat_id: int, text: str) -> None:
    """Send LAST response."""
    items = _get_dx_snapshot()
    if not items:
        _tg_send(chat_id, "\u2139\uFE0F No DX snapshot yet.")
        return

    # Parse limit
    parts = text.strip().split()
    n = 1
    if len(parts) >= 2 and parts[1].isdigit():
        n = max(1, min(20, int(parts[1])))

    # Sort by time descending
    items_with_time = [it for it in items if it.get("time")]
    if items_with_time:
        items_with_time.sort(key=lambda x: x.get("time", ""), reverse=True)
        items = items_with_time[:n]
    else:
        items = items[:n]

    now = datetime.now().strftime("%d/%m %H:%M")
    header = f"\u23F1\uFE0F LAST \u2014 {now} ({len(items)})"

    lines = []
    for it in items:
        ch = it.get("channel", "?")
        dist = it.get("distance")
        snr = it.get("snr_max")

        db = _get_distance_badge(dist)
        sb = _get_snr_badge(snr)

        dist_txt = f"{dist:5.1f}km" if dist is not None else "  ?km"
        snr_txt = f"{snr:4.1f}dB{sb}" if snr is not None else f"  ?dB{sb}"
        hh = _hhmm(it.get("time", ""))

        lines.append(f"{db} {ch:>3}  {dist_txt:>8}  {snr_txt:>8}  {hh:>5}  {_cut(it.get('label', ''), 18):<18}  {_cut(it.get('location', ''), 26)}")

    _tg_send(chat_id, header + "\n```text\n" + "\n".join(lines) + "\n```")


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
            return "\U0001F7EA"  # 🟪 Purple square
        elif d > 100:
            return "\U0001F7E7"  # 🟧 Orange square
        else:
            return "\U0001F7E9"  # 🟩 Green square
    except Exception:
        return "\u2B1C"  # ⬜ White square


def _get_snr_badge(snr) -> str:
    """Get emoji badge for SNR."""
    try:
        v = float(snr)
        if v < 6:
            return "\U0001F7E5"  # 🟥 Red square
        elif v < 10:
            return "\U0001F7E7"  # 🟧 Orange square
        else:
            return "\U0001F7E9"  # 🟩 Green square
    except Exception:
        return "\u2B1C"  # ⬜ White square
