"""Telegram bot API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...config import get_config
from pydantic import BaseModel

from ...core.telegram_bot import (
    start_telegram_bot,
    stop_telegram_bot,
    is_bot_running,
    get_bot_stats,
    send_test_message,
)


class TelegramTestRequest(BaseModel):
    token: str
    chat_id: str

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status")
async def get_telegram_status():
    """Get Telegram bot status."""
    config = get_config()
    running = is_bot_running()
    stats = get_bot_stats()

    return {
        "running": running,
        "enabled": config.telegram.enabled,
        "token_configured": bool(config.telegram.token),
        "stats": stats,
    }


@router.post("/start")
async def start_bot():
    """Start the Telegram bot."""
    config = get_config()

    if not config.telegram.token:
        raise HTTPException(
            status_code=400,
            detail="Telegram token not configured"
        )

    if is_bot_running():
        return {"success": True, "message": "Bot already running"}

    try:
        start_telegram_bot()
        return {"success": True, "message": "Bot started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_bot():
    """Stop the Telegram bot."""
    if not is_bot_running():
        return {"success": True, "message": "Bot not running"}

    try:
        stop_telegram_bot()
        return {"success": True, "message": "Bot stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart")
async def restart_bot():
    """Restart the Telegram bot."""
    config = get_config()

    if not config.telegram.token:
        raise HTTPException(
            status_code=400,
            detail="Telegram token not configured"
        )

    try:
        if is_bot_running():
            stop_telegram_bot()

        start_telegram_bot()
        return {"success": True, "message": "Bot restarted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_bot(req: TelegramTestRequest):
    """Send a test message via Telegram bot."""
    # Use real token from config if submitted value is masked
    token = req.token
    if not token or token.endswith("..."):
        config = get_config()
        token = config.telegram.token

    if not token:
        return {"success": False, "message": "Token non configuré"}

    if not req.chat_id:
        return {"success": False, "message": "Chat ID non renseigné"}

    try:
        result = send_test_message(token, req.chat_id)
        if result:
            return {"success": True, "message": "Message de test envoyé"}
        else:
            return {"success": False, "message": "Échec de l'envoi. Vérifiez le token et le chat ID."}
    except Exception as e:
        return {"success": False, "message": str(e)}
