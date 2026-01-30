#!/usr/bin/env python3
"""
AbracaDABra Logger WebUI - Entry Point

Usage:
    python run.py
    python run.py --host 0.0.0.0 --port 8080
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="AbracaDABra Logger WebUI")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is not installed.")
        print("Please install dependencies: pip install -r requirements.txt")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           AbracaDABra Logger WebUI                           ║
╠══════════════════════════════════════════════════════════════╣
║  Local:   http://127.0.0.1:{args.port:<5}                          ║
║  Network: http://<your-ip>:{args.port:<5}                          ║
╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="debug" if args.debug else "info",
    )


if __name__ == "__main__":
    main()
