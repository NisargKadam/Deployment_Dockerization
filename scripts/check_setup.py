"""Print safe configuration diagnostics. Never prints credential values."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.telemetry import get_langsmith_client, tracing_enabled

parser = argparse.ArgumentParser()
parser.add_argument(
    "--verify-langsmith", action="store_true", help="Read workspace API to verify access"
)
args = parser.parse_args()
print(f"Mode: {settings.app_mode} | Port: {settings.port} | Environment: {settings.environment}")
print("OpenAI key:", "present" if settings.openai_api_key else "missing")
print("LangSmith key:", "present" if settings.langsmith_api_key else "missing")
print("Tracing:", "enabled" if tracing_enabled() else "off")
print("Project:", settings.langsmith_project)
print("Input/output hiding:", settings.langsmith_hide_inputs, settings.langsmith_hide_outputs)
if args.verify_langsmith:
    client = get_langsmith_client()
    if not client:
        sys.exit("Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env first.")
    try:
        list(client.list_projects(limit=1))
        print("LangSmith workspace access verified. Submit a request to verify trace ingestion.")
    except Exception as error:
        sys.exit(
            f"LangSmith access failed ({type(error).__name__}). Check key, region and workspace."
        )
