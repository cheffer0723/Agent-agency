# FastAPI entrypoint for hosting (Railway, Docker, Agencii, etc.).
# Serves a chat UI at / and the agency API under /my-agency/*.

import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

logging.basicConfig(level=logging.INFO)

from agency import create_agency
from agency_swarm.integrations.fastapi import run_fastapi

PORT = int(os.getenv("PORT", "8080"))
STATIC_DIR = Path(__file__).resolve().parent / "static"


def build_app():
    app = run_fastapi(
        agencies={
            "my-agency": create_agency,
        },
        host="0.0.0.0",
        port=PORT,
        enable_logging=True,
        return_app=True,
    )

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def chat_ui():
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
