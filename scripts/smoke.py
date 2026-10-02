"""Submit fictional classroom text and optionally confirm its trace was ingested."""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.telemetry import get_langsmith_client

parser = argparse.ArgumentParser()
parser.add_argument("--url", default="http://localhost:8010")
parser.add_argument("--scenario", choices=["normal", "slow", "error"], default="normal")
parser.add_argument("--verify-trace", action="store_true")
args = parser.parse_args()
body = json.dumps(
    {
        "text": "Furthermore, it is important to note that we utilize containers in order to deploy the same application consistently.",
        "scenario": args.scenario,
    }
).encode()
headers = {"Content-Type": "application/json"}
if settings.class_access_token:
    headers["X-Class-Token"] = settings.class_access_token.get_secret_value()
request = urllib.request.Request(args.url.rstrip("/") + "/humanize", body, headers)
try:
    response = urllib.request.urlopen(request, timeout=180)
except urllib.error.HTTPError as error:
    response = error
except urllib.error.URLError:
    sys.exit("Could not reach the app. Start it and check --url / port before running this script.")
payload = json.load(response)
print("HTTP", response.status)
expected = 502 if args.scenario == "error" else 200
if response.status != expected:
    sys.exit("Unexpected response; inspect app configuration and the server logs.")
result = payload.get("detail", payload)
print("Request:", result.get("request_id"))
print("Latency:", result.get("duration_ms"), "ms")
print("Trace:", result.get("trace", {}).get("status"))
print("URL:", result.get("trace", {}).get("url"))
if args.verify_trace:
    client = get_langsmith_client()
    if not client or not result.get("trace", {}).get("id"):
        sys.exit("Tracing is off on the client or server.")
    for _attempt in range(15):
        try:
            run = client.read_run(result["request_id"], load_child_runs=True)
            if run.end_time:
                print("VERIFIED: root trace ingested; status:", "error" if run.error else "success")
                print("Immediate child spans:", len(run.child_runs or []))
                if bool(run.error) != (args.scenario == "error"):
                    sys.exit("Unexpected trace error status")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        sys.exit("Trace not visible yet. Check region, workspace, project and SDK upload logs.")
