"""FastAPI entry point — bootstrap-stage health endpoint only."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from nl_sql import __version__
from nl_sql.config import get_settings


class HealthResponse(BaseModel):
    status: str
    version: str
    providers_configured: list[str]


def create_app() -> FastAPI:
    app = FastAPI(
        title="NL→SQL Assistant",
        version=__version__,
        description="Portfolio demo: NL→SQL with measurable accuracy + safety guards.",
    )
    settings = get_settings()

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        configured: list[str] = []
        if settings.mistral_api_key:
            configured.append("mistral")
        if settings.github_token:
            configured.append("github_models")
        if settings.groq_api_key:
            configured.append("groq")
        configured.append("ollama")
        return HealthResponse(
            status="ok",
            version=__version__,
            providers_configured=sorted(configured),
        )

    return app


app = create_app()
