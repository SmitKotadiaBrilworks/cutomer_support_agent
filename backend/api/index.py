"""Vercel Python Function entrypoint for the single-project deployment.

The root `vercel.json` routes every `/api/*` request here, but the actual
HTTP path forwarded to this function is NOT stripped of that prefix (Vercel
just chooses which function handles the request; the ASGI scope still sees
the original path, e.g. "/api/chat"). Mounting the real app under "/api"
lets Starlette strip that prefix internally, so `app/main.py`'s own routes
stay exactly as they are (`/health`, `/chat`, `/agents`) — unprefixed and
identical to how they're served locally via `uvicorn app.main:app`.

The sys.path append is needed because Vercel invokes this file directly
(its own directory is sys.path[0]), while `app` is a sibling top-level
package one level up.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402

from app.main import app as backend_app  # noqa: E402

app = FastAPI()
app.mount("/api", backend_app)
