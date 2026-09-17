# FastAPI entrypoint for hosting (Railway, Docker, Agencii, etc.).
# Keep create_agency exported via agency.py — hosts call that factory per request.

import logging
import os

from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

from agency import create_agency
from agency_swarm.integrations.fastapi import run_fastapi

# Railway (and most PaaS) inject PORT; default 8080 for local/Docker.
PORT = int(os.getenv("PORT", "8080"))


if __name__ == "__main__":
    run_fastapi(
        agencies={
            # Endpoint prefix: POST /my-agency/get_response
            "my-agency": create_agency,
        },
        host="0.0.0.0",
        port=PORT,
        enable_logging=True,
    )