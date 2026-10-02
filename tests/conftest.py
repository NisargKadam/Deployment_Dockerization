"""Tests never use local credentials, make model calls, or export traces."""

import os

os.environ["OPENAI_API_KEY"] = " "
os.environ["LANGSMITH_API_KEY"] = " "
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["APP_MODE"] = "live"
os.environ["ENABLE_DEMO_SCENARIOS"] = "false"
os.environ["CLASS_ACCESS_TOKEN"] = " "

import pytest


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "class_access_token", None)
