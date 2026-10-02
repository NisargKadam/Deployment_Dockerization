import json
import logging
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.config import settings
from app.logging_conf import JsonFormatter
from app.main import app
from app.telemetry import get_langsmith_client


@pytest.fixture
async def client():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setattr(settings, "app_mode", "demo")
    monkeypatch.setattr(settings, "enable_demo_scenarios", True)


async def test_demo_request_has_correlated_id_real_timings_and_no_fake_tokens(client, demo):
    response = await client.post(
        "/humanize", json={"text": "We utilize containers in order to deploy."}
    )
    assert response.status_code == 200
    data = response.json()
    assert UUID(data["request_id"])
    assert response.headers["X-Request-ID"] == data["request_id"]
    assert data["text"] == "We use containers to deploy."
    assert data["passes"] == 2
    assert [step["name"] for step in data["steps"]] == ["rewrite", "evaluate"] * 2
    assert all(step["duration_ms"] > 0 for step in data["steps"])
    assert data["duration_ms"] >= sum(step["duration_ms"] for step in data["steps"])
    assert data["usage"] is None
    assert data["trace"]["status"] == "off"


async def test_error_scenario_preserves_request_correlation(client, demo):
    response = await client.post("/humanize", json={"text": "Example.", "scenario": "error"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["request_id"] == response.headers["X-Request-ID"]
    assert "Intentional demo error" in detail["message"]


async def test_scenarios_are_explicitly_gated(client, monkeypatch, demo):
    monkeypatch.setattr(settings, "enable_demo_scenarios", False)
    response = await client.post("/humanize", json={"text": "Example.", "scenario": "error"})
    assert response.status_code == 400


async def test_whitespace_and_unknown_scenarios_rejected(client):
    for body in [{"text": "   "}, {"text": "Example", "scenario": "arbitrary"}]:
        assert (await client.post("/humanize", json=body)).status_code == 422


async def test_access_token_blocks_requests_but_not_health(client, monkeypatch, demo):
    monkeypatch.setattr(settings, "class_access_token", SecretStr("class-test"))
    assert (await client.get("/health")).status_code == 200
    assert (await client.post("/humanize", json={"text": "Example"})).status_code == 401
    assert (
        await client.post(
            "/humanize", json={"text": "Example"}, headers={"X-Class-Token": "class-test"}
        )
    ).status_code == 200


async def test_public_config_never_exposes_credentials(client, monkeypatch):
    monkeypatch.setattr(settings, "langsmith_api_key", SecretStr("private-langsmith-test"))
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("private-openai-test"))
    monkeypatch.setattr(settings, "class_access_token", SecretStr("private-access-test"))
    response = await client.get("/api/config")
    assert "private-" not in response.text
    assert response.json()["access_token_required"] is True


async def test_guide_served_as_self_contained_html(client):
    response = await client.get("/guide")
    assert response.status_code == 200
    assert "Deployments and observability" in response.text
    assert "<script src=" not in response.text


async def test_live_provider_errors_do_not_leak_payloads(client, monkeypatch, caplog):
    class BrokenGraph:
        async def ainvoke(self, *args, **kwargs):
            raise ValueError("private-provider-payload")

    monkeypatch.setattr(settings, "openai_api_key", SecretStr("test-key"))
    monkeypatch.setattr("app.api.routes.get_humanizer_graph", BrokenGraph)
    with caplog.at_level(logging.ERROR):
        response = await client.post("/humanize", json={"text": "Example"})
    assert response.status_code == 502
    assert "private-provider-payload" not in response.text
    assert "private-provider-payload" not in caplog.text


async def test_langsmith_parent_and_children_use_configured_client(client, demo, monkeypatch):
    from langsmith import Client

    sdk = Client(api_key="fake-local-test", auto_batch_tracing=False, info={})
    created, updated = [], []
    monkeypatch.setattr(Client, "create_run", lambda *args, **kw: created.append(kw))
    monkeypatch.setattr(Client, "update_run", lambda *args, **kw: updated.append((args, kw)))
    monkeypatch.setattr(
        Client, "get_run_url", lambda *args, **kw: "https://smith.langchain.com/test-run"
    )
    monkeypatch.setattr("app.api.routes.get_langsmith_client", lambda: sdk)
    response = await client.post("/humanize", json={"text": "Example"})
    assert response.status_code == 200
    data = response.json()
    assert data["trace"]["id"] == data["request_id"]
    assert data["trace"]["status"].startswith("queued")
    root = next(run for run in created if run.get("name") == "humanize.request")
    graph = next(run for run in created if run.get("name") == "humanizer.graph")
    assert str(root["id"]) == data["request_id"]
    assert graph["parent_run_id"] == root["id"]
    assert {"demo_writer", "demo_evaluator", "rewrite", "evaluate"} <= {
        run.get("name") for run in created
    }
    assert updated


def test_zero_values_are_not_dropped_from_logs():
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "done", (), None)
    record.input_tokens = 0
    record.score = 0
    assert json.loads(JsonFormatter().format(record))["input_tokens"] == 0


def test_disabled_tracing_does_not_construct_client():
    get_langsmith_client.cache_clear()
    assert get_langsmith_client() is None
