"""Vercel Python Function entrypoint.

Vercel's Python runtime detects an ASGI app named `app` in this file and
serves it directly (the same FastAPI instance used by `uvicorn` locally) —
no adapter/WSGI shim needed. `vercel.json` in the parent directory rewrites
every request to this function, so FastAPI's own router (not Vercel) decides
what `/chat`, `/health`, etc. resolve to.

The path append below is needed because Vercel invokes this file directly
(its own directory is sys.path[0]), while `app` is a sibling top-level
package one level up — the same layout `uvicorn app.main:app` relies on when
run from `backend/` locally.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402
