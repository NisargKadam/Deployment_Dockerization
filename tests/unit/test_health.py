import json
import logging
from time import perf_counter

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.logging_conf import JsonFormatter
from app.main import app


@pytest.mark.asyncio
async def test_health_is_dependency_free_and_fast() -> None:
    # The installed Starlette TestClient warns that its HTTPX integration is deprecated.
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/health")
        started = perf_counter()
        responses = [await client.get("/health") for _ in range(5)]
        elapsed_per_request = (perf_counter() - started) / len(responses)

    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == {"status": "ok"} for response in responses)
    assert elapsed_per_request < 0.005


@pytest.mark.asyncio
async def test_ready_is_separate_from_liveness_without_a_key() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "checks": {"config": False}}


@pytest.mark.asyncio
async def test_docs_are_available() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/docs")).status_code == 200


@pytest.mark.asyncio
async def test_ui_and_static_assets_are_served_by_the_api() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/")
        stylesheet = await client.get("/static/styles.css")
        script = await client.get("/static/app.js")

    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Keep the meaning" in page.text
    assert stylesheet.status_code == 200
    assert "--violet" in stylesheet.text
    assert script.status_code == 200
    assert 'fetch("/humanize"' in script.text


@pytest.mark.asyncio
async def test_humanize_requires_an_api_key() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/humanize", json={"text": "Please rewrite this."})

    assert response.status_code == 503
    assert response.json() == {"detail": "OPENAI_API_KEY is not configured"}


@pytest.mark.asyncio
async def test_humanize_returns_the_graph_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGraph:
        async def ainvoke(self, state: dict[str, object], **_kwargs) -> dict[str, object]:
            return {**state, "current_text": "A natural rewrite.", "score": 91.0, "passes": 2}

    monkeypatch.setattr("app.api.routes.settings.openai_api_key", SecretStr("test-key"))
    monkeypatch.setattr("app.api.routes.get_humanizer_graph", FakeGraph)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/humanize",
            json={"text": "Please rewrite this.", "audience": "engineers", "tone": "direct"},
        )

    assert response.status_code == 200
    data = response.json()
    assert {key: data[key] for key in ("text", "score", "passes", "model")} == {
        "text": "A natural rewrite.",
        "score": 91.0,
        "passes": 2,
        "model": "gpt-4.1-mini",
    }


def test_settings_reject_an_invalid_port() -> None:
    try:
        Settings(_env_file=None, port=0)
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid ports must fail at boot")


def test_log_formatter_emits_json() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "service ready", (), None)
    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "INFO"
    assert payload["message"] == "service ready"
