"""FastAPI application for AbracaDABra Logger WebUI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import get_config
from .api.routes import status, dx_data, map_data, config, telegram
from .core.telegram_bot import start_telegram_bot, stop_telegram_bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    cfg = get_config()

    # Start Telegram bot if enabled
    if cfg.telegram.enabled and cfg.telegram.token:
        try:
            start_telegram_bot()
            print("Telegram bot started")
        except Exception as e:
            print(f"Failed to start Telegram bot: {e}")

    yield

    # Shutdown
    stop_telegram_bot()
    print("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="AbracaDABra Logger WebUI",
    description="Web interface for AbracaDABra DAB radio logging",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for LAN access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=templates_dir)

# Include API routers
app.include_router(status.router)
app.include_router(dx_data.router)
app.include_router(map_data.router)
app.include_router(config.router)
app.include_router(telegram.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main web interface."""
    cfg = get_config()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": cfg,
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
