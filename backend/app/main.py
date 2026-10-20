"""ASGI entry point: `uvicorn app.main:app` (see `make run`)."""

from app.api import create_app

app = create_app()
