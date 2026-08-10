"""FastAPI surface for the GraphFixture Proof Pipeline."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from graphfixture.web_service import LiveDataHubError, ProofService
from graphfixture.web_view import proof_view

PACKAGE_DIR = Path(__file__).resolve().parent


class RunRequest(BaseModel):
    variant: Literal["broken", "fixed"] = "broken"
    source: Literal["offline", "live"] = "offline"
    seed: int = Field(default=42, ge=0, le=2_147_483_647)


def create_app(
    service: ProofService | None = None,
    *,
    enable_live: bool | None = None,
) -> FastAPI:
    proof_service = service or ProofService()
    live_enabled = (
        os.getenv("GRAPHFIXTURE_ENABLE_LIVE_WEB", "false").lower() in {"1", "true", "yes"}
        if enable_live is None
        else enable_live
    )
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    app = FastAPI(title="GraphFixture", version="0.1.0")
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"service": "graphfixture", "status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        outcome = proof_service.execute("broken", "offline")
        initial = proof_view(outcome)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"initial": initial},
        )

    @app.post("/api/run")
    async def run_proof(body: RunRequest) -> dict[str, object]:
        if body.source == "live" and not live_enabled:
            raise HTTPException(
                status_code=503,
                detail="live DataHub runs are disabled on this public deployment",
            )
        try:
            outcome = proof_service.execute(body.variant, body.source, body.seed)
            return proof_view(outcome)
        except LiveDataHubError as exc:
            raise HTTPException(
                status_code=503,
                detail="live DataHub proof is unavailable; use offline synthetic replay",
            ) from exc

    return app


app = create_app()
