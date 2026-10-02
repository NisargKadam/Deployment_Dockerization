"""The classroom API: a real graph, correlated logs, and nested LangSmith traces."""

import asyncio
import hmac
import logging
from functools import lru_cache
from time import perf_counter
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from langsmith import trace, tracing_context
from pydantic import BaseModel, Field, field_validator

from app.agent import create_humanizer_graph
from app.agent.demo import DemoFailure, create_demo_graph
from app.config import settings
from app.telemetry import TokenUsage, get_langsmith_client, tracing_enabled

router = APIRouter()
logger = logging.getLogger(__name__)


class HumanizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=settings.max_input_chars)
    audience: str = Field(default="general", min_length=1, max_length=100)
    tone: str = Field(default="natural and conversational", min_length=1, max_length=100)
    scenario: Literal["normal", "slow", "error"] = "normal"

    @field_validator("text")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter some text first")
        return value


class HumanizeResponse(BaseModel):
    text: str
    score: float
    passes: int
    model: str
    mode: str
    request_id: str
    duration_ms: float
    steps: list[dict[str, Any]]
    usage: dict[str, int] | None
    trace: dict[str, Any]


@router.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


def model_configured() -> bool:
    return bool(settings.openai_api_key and settings.openai_api_key.get_secret_value().strip())


@router.get("/ready", tags=["operations"])
async def ready() -> JSONResponse:
    is_ready = settings.app_mode == "demo" or model_configured()
    return JSONResponse(
        {"status": "ready" if is_ready else "not_ready", "checks": {"config": is_ready}},
        status_code=200 if is_ready else 503,
    )


@router.get("/api/config", tags=["operations"])
async def public_config() -> dict[str, Any]:
    # Configuration presence is not proof of successful ingestion.
    return {
        "mode": settings.app_mode,
        "environment": settings.environment,
        "model": settings.openai_model if settings.app_mode == "live" else "demo (no LLM)",
        "model_configured": model_configured(),
        "max_input_chars": settings.max_input_chars,
        "max_passes": settings.max_passes,
        "score_threshold": settings.score_threshold,
        "scenarios_enabled": settings.enable_demo_scenarios and settings.app_mode == "demo",
        "access_token_required": bool(settings.class_access_token),
        "tracing": {
            "enabled": tracing_enabled(),
            "project": settings.langsmith_project,
            "status": "configured · delivery unverified" if tracing_enabled() else "off",
            "hide_inputs": settings.langsmith_hide_inputs,
            "hide_outputs": settings.langsmith_hide_outputs,
        },
    }


@lru_cache(maxsize=1)
def get_humanizer_graph():
    return create_humanizer_graph(settings)


@router.post("/humanize", response_model=HumanizeResponse, tags=["agent"])
async def humanize(
    request: HumanizeRequest,
    response: Response,
    x_class_token: str | None = Header(default=None),
) -> HumanizeResponse:
    if settings.class_access_token and not hmac.compare_digest(
        (x_class_token or "").encode(), settings.class_access_token.get_secret_value().encode()
    ):
        raise HTTPException(401, "Enter the class access token supplied by your instructor")
    if settings.app_mode == "live" and not model_configured():
        raise HTTPException(503, "OPENAI_API_KEY is not configured")
    if request.scenario != "normal" and not (
        settings.app_mode == "demo" and settings.enable_demo_scenarios
    ):
        raise HTTPException(
            400, "Rehearsal scenarios require demo mode and ENABLE_DEMO_SCENARIOS=true"
        )

    request_id = uuid4()
    started = perf_counter()
    client = get_langsmith_client()
    usage = TokenUsage()
    metadata = {
        "request_id": str(request_id),
        "environment": settings.environment,
        "mode": settings.app_mode,
        "scenario": request.scenario,
        "service": settings.app_name,
        "lesson": "Deployments and observability",
    }
    trace_info: dict[str, Any] = {
        "id": str(request_id) if client else None,
        "status": "queued · delivery unverified" if client else "off",
        "url": None,
        "project": settings.langsmith_project,
    }
    response.headers["X-Request-ID"] = str(request_id)
    run = None
    try:
        with tracing_context(
            enabled=bool(client), client=client, project_name=settings.langsmith_project
        ):
            with trace(
                "humanize.request",
                run_id=request_id,
                inputs=request.model_dump(),
                metadata=metadata,
                tags=[settings.environment, settings.app_mode, f"scenario:{request.scenario}"],
                client=client,
                project_name=settings.langsmith_project,
            ) as run:
                graph = (
                    create_demo_graph(settings, request.scenario)
                    if settings.app_mode == "demo"
                    else get_humanizer_graph()
                )
                result = await graph.ainvoke(
                    {
                        "original_text": request.text,
                        "current_text": request.text,
                        "audience": request.audience,
                        "tone": request.tone,
                        "feedback": [],
                        "score": 0.0,
                        "passes": 0,
                        "steps": [],
                    },
                    config={
                        "run_name": "humanizer.graph",
                        "metadata": metadata,
                        "callbacks": [usage],
                    },
                )
                run.end(
                    outputs={
                        "text": result["current_text"],
                        "score": result["score"],
                        "passes": result["passes"],
                    }
                )
                # URL construction may need workspace/project lookup; never block the event loop.
                if client:
                    try:
                        trace_info["url"] = await asyncio.to_thread(
                            client.get_run_url, run=run, project_name=settings.langsmith_project
                        )
                    except Exception:
                        logger.warning(
                            "Trace link unavailable", extra={"event": "telemetry.link_failed"}
                        )
    except Exception as exc:
        if client and run is not None:
            try:
                trace_info["url"] = await asyncio.to_thread(
                    client.get_run_url, run=run, project_name=settings.langsmith_project
                )
            except Exception:
                logger.warning("Trace link unavailable", extra={"event": "telemetry.link_failed"})
        duration = round((perf_counter() - started) * 1000, 1)
        logger.error(
            "humanizer workflow failed",
            extra={
                "event": "humanizer.failed",
                **metadata,
                "duration_ms": duration,
                "error_type": type(exc).__name__,
            },
        )
        # Full exception stays in LangSmith; stdout never includes prompt/provider payloads.
        raise HTTPException(
            502,
            detail={
                "message": "Intentional demo error. Inspect demo_writer in LangSmith."
                if isinstance(exc, DemoFailure)
                else "The model request failed. Inspect the trace.",
                "request_id": str(request_id),
                "mode": settings.app_mode,
                "duration_ms": duration,
                "trace": trace_info,
            },
            headers={"X-Request-ID": str(request_id)},
        ) from exc

    duration = round((perf_counter() - started) * 1000, 1)
    logger.info(
        "humanizer workflow completed",
        extra={
            "event": "humanizer.completed",
            **metadata,
            "duration_ms": duration,
            "passes": result["passes"],
            "score": result["score"],
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
    )
    return HumanizeResponse(
        text=result["current_text"],
        score=result["score"],
        passes=result["passes"],
        model=settings.openai_model if settings.app_mode == "live" else "demo (no LLM)",
        mode=settings.app_mode,
        request_id=str(request_id),
        duration_ms=duration,
        steps=result.get("steps", []),
        usage={
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "llm_calls": usage.calls,
        }
        if settings.app_mode == "live"
        else None,
        trace=trace_info,
    )
