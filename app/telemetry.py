"""Explicit LangSmith configuration; .env is read by Settings, not SDK globals."""

import logging
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langsmith import Client

from app.config import settings

logger = logging.getLogger(__name__)


def tracing_enabled() -> bool:
    return bool(
        settings.langsmith_tracing
        and settings.langsmith_api_key
        and settings.langsmith_api_key.get_secret_value().strip()
    )


def report_trace_error(_error: Exception) -> None:
    # Never serialize SDK exceptions: they may contain traced payloads.
    logger.warning(
        "LangSmith upload failed; check key, region, and workspace",
        extra={"event": "telemetry.upload_failed"},
    )


@lru_cache(maxsize=1)
def get_langsmith_client() -> Client | None:
    if not tracing_enabled():
        return None
    return Client(
        api_key=settings.langsmith_api_key.get_secret_value(),
        api_url=settings.langsmith_endpoint,
        workspace_id=settings.langsmith_workspace_id or None,
        hide_inputs=settings.langsmith_hide_inputs,
        hide_outputs=settings.langsmith_hide_outputs,
        timeout_ms=5000,
        tracing_error_callback=report_trace_error,
    )


class TokenUsage(BaseCallbackHandler):
    """Sum provider-reported tokens across writer and evaluator calls."""

    run_inline = True

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.calls += 1
        for generations in response.generations:
            for generation in generations:
                usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                if usage:
                    self.input_tokens += usage.get("input_tokens", 0)
                    self.output_tokens += usage.get("output_tokens", 0)
