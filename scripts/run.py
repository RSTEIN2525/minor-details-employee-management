#!/usr/bin/env python3
"""Script to run the FastAPI application using Uvicorn."""

import uvicorn
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Get host and port from environment variables or use defaults
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))
    APP_RELOAD = os.getenv("APP_RELOAD", "True").lower() in ("true", "1", "t")
    APP_LOG_LEVEL = os.getenv("APP_LOG_LEVEL", "info")

    print(f"Starting Uvicorn server on {APP_HOST}:{APP_PORT}")
    print(f"Reloading: {APP_RELOAD}")
    print(f"Log level: {APP_LOG_LEVEL}")

    uvicorn.run(
        "main:app", 
        host=APP_HOST, 
        port=APP_PORT, 
        reload=APP_RELOAD, 
        log_level=APP_LOG_LEVEL,
        app_dir=PROJECT_ROOT,
        reload_dirs=[PROJECT_ROOT] # Also tell reloader to watch the project root
    )
