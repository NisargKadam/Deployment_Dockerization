# Deployments and observability

A classroom lab built from [NisargKadam/Deployment_Dockerization](https://github.com/NisargKadam/Deployment_Dockerization).
The Humanizer app runs a bounded LangGraph rewrite/review workflow. Students investigate it in
LangSmith, build a Docker image, run a container, and deploy to Railway. Azure and AWS include optional CLI deployment walkthroughs; no cloud infrastructure is provisioned by generating the guide.

**Start with the [standalone HTML class guide](app/static/guide.html)**. It is also served at `/guide`.
It includes a 90-minute lesson plan, copyable commands, expected results, presenter view, topic
search, progress checkboxes, quizzes, troubleshooting, and print styling. No CDN or build tool is
needed to open it offline.

## Run locally

Python 3.12 is the tested version. From this directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.example .env   # Only on first setup; do not overwrite an existing .env
python -m app.main
```

Windows equivalents are in the guide. Open **http://localhost:8010**. `PORT=8010` in the example
avoids conflicting with other services on 8000. Without an env file, the Python default is 8000.

The example starts in **demo mode**: deterministic text replacements, synthetic review scores,
measured timings, no model calls. Set `APP_MODE=live` and `OPENAI_API_KEY` for actual OpenAI calls.
Restart after changing `.env`.

## Connect LangSmith

Create a key in your own LangSmith workspace and configure `.env` privately:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=your_private_key
LANGSMITH_PROJECT=deployments-observability
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
```

Use the correct regional endpoint and set `LANGSMITH_WORKSPACE_ID` when your key requires it.
The backend creates an explicit SDK client, so the `.env` values do not depend on global SDK env loading.

```bash
python scripts/check_setup.py --verify-langsmith
python scripts/smoke.py --verify-trace
```

The first command checks workspace access. The second submits fictional text and polls for its
completed trace. This spends model credits if the server is in live mode. The pinned SDK currently
warns that its `read_run` method is deprecated; it remains supported in this version.

- Root trace: `humanize.request`, with a UUID also returned in `X-Request-ID` and the response body.
- Nested graph: `humanizer.graph`, rewrite/evaluate nodes, and actual model calls in live mode.
- Metadata/tags: mode, environment, scenario, service, lesson, and request ID.
- JSON logs: correlated completion/failure events, latency, score, passes, provider token counts.
- UI: measured latency/step durations, model call count, input/output tokens, authenticated trace link.
- Trace delivery is asynchronous. **Configured or queued is not a delivery confirmation**.
- In demo mode, enable `ENABLE_DEMO_SCENARIOS=true` for normal, slow-writer, and intentional-error runs.
- API keys remain on the server. `LANGSMITH_HIDE_INPUTS/OUTPUTS=true` hide ordinary traced payloads;
  error strings and metadata need separate consideration. Use fictional classroom text.

The model review score is an opinion, not an AI detector or a guarantee of factual accuracy.
Live calls may run up to two model calls per pass, plus provider retries. `REQUEST_TIMEOUT_SECONDS`
is per provider request, not a total workflow deadline. LangSmith supplies supported model cost
estimates; the application does not invent prices or token usage.

## Docker

Run these commands in `Deployment_Dockerization`, the folder containing `Dockerfile`.
Activating `.venv` does **not** change directories, and Docker does not need the virtualenv.
This block works from either the parent `Deployments` folder or the project folder (macOS/Linux):

```bash
if [ -d Deployment_Dockerization ]; then cd Deployment_Dockerization; fi
pwd
ls Dockerfile .env
```

Start Docker Desktop first (`open -a Docker` on macOS). Wait until `docker version` shows
both **Client** and **Server**. A missing `docker.sock` means the engine is not ready yet.

```bash
docker info >/dev/null && docker build -t humanizer-lab:1.0 .
docker image ls humanizer-lab
docker history humanizer-lab:1.0
```

Only continue after a successful build: an existing image with this tag can be left over from
an earlier rehearsal. Before repeating the create step, check `docker ps -a --filter name=humanizer-class`.
If the classroom container already exists, run `docker stop humanizer-class` followed by
`docker rm humanizer-class` to recreate it with the newly built image. This removes that
container's writable layer; this app does not persist drafts.

```bash
docker create --name humanizer-class --env-file .env -e PORT=8000 -e ENVIRONMENT=docker -p 127.0.0.1:8011:8000 humanizer-lab:1.0
docker start humanizer-class
```

Open **http://localhost:8011**. The internal port is 8000; the host port is 8011.
The container uses the mode in `.env`. For a rehearsal without model calls, add
`-e APP_MODE=demo` to `docker create` before the image name.

```bash
curl --fail --retry 10 --retry-all-errors --retry-delay 1 http://localhost:8011/health
docker logs --tail 30 humanizer-class
docker inspect --format '{{.State.Health.Status}}' humanizer-class
```

Health may initially show `starting`; allow a probe interval for `healthy`.
With the local virtualenv activated, run `python scripts/smoke.py --url http://localhost:8011`.
Add `--verify-trace` only when LangSmith is configured and tracing is enabled.

Or use `docker compose up --build -d` (stop the named container first to free port 8011).
The image runs as a non-root user, includes `/guide`, and excludes `.env`, Git history, and the local
virtualenv. `requirements.lock` pins transitive runtime dependencies for consistent builds;
`requirements.txt` lists the direct dependencies. Refresh the lock intentionally with
`uv pip compile requirements.txt -o requirements.lock --python-version 3.12 --universal`.

Rebuild/recreate after code changes. Recreate after environment changes; restarting alone does not
pick up a new env file.

## Railway

The guide covers both CLI upload and GitHub integration. CLI upload can deploy this checkout before
the classroom branch is published to GitHub.

```bash
railway login
railway init --name deployments-observability
railway add --service humanizer
railway service link humanizer
# Add runtime variables privately in the service's Variables tab.
railway up
railway domain
```

`railway.json` selects the Dockerfile and `/health` deployment check. The app listens on `0.0.0.0`
and reads Railway's `PORT`. Use `ENVIRONMENT=railway` to identify cloud traces.

Set `CLASS_ACCESS_TOKEN` for a shared classroom guard on `/humanize`; the UI reveals a password
field when required. A public live model service needs this guard and, for use beyond class,
proper authentication, rate limiting, and budgets. `/health`, `/guide`, and `/api/config` do not
expose credentials. Health/readiness only check process/configuration, not provider connectivity.

## Verify and maintain

```bash
python -m pytest
python -m ruff check .
python -m ruff format --check .
node --check app/static/app.js
python scripts/build_guide.py
```

Tests use fake models and isolate local credentials. They cover graph bounds, API responses,
request correlation, scenario gating, token access, secret-safe configuration, provider error
handling, and LangSmith parent/child instrumentation without sending traces.

Edit `scripts/build_guide.py` and regenerate the HTML. Dockerfile and Railway examples are embedded
from their actual files. Keep the generated `app/static/guide.html` in the repository.

## Main files

| File | Teaching purpose |
| --- | --- |
| `app/agent/workflow.py` | Real rewrite/evaluate loop |
| `app/agent/demo.py` | Deterministic classroom scenarios |
| `app/telemetry.py` | Explicit LangSmith client + usage callback |
| `app/api/routes.py` | Root trace + request ID + API |
| `app/static/` | App UI and self-contained guide |
| `Dockerfile` / `compose.yaml` | Image build and local containers |
| `railway.json` | Cloud build/deployment configuration |
| `scripts/check_setup.py` / `scripts/smoke.py` | Safe diagnostics + trace verification |

The classroom version is on branch `class/deployments-observability`. Students should clone it with:

```bash
git clone --branch class/deployments-observability https://github.com/NisargKadam/Deployment_Dockerization.git
```

## Prepared instructor session (2 October 2026)

- Live OpenAI app: http://localhost:8010 (the current private `.env` selects live mode).
- Docker rehearsal: http://localhost:8011 (`humanizer-class`, `humanizer-lab:1.0`, explicit demo-mode override).
- Guide: http://localhost:8010/guide or open `app/static/guide.html` directly.
- LangSmith: [deployments-observability](https://smith.langchain.com/o/607d09f9-3e9c-40c5-85e9-0bda273c82c2/projects/p/479cdd60-3e00-4396-b17a-cdba626f75c9).

Verified: 21 automated tests; lint and format checks; real OpenAI trace with nested model calls,
tokens and cost; normal/slow/error demo traces; Docker build, health, non-root user, and trace export;
UI result rendering, guide quiz feedback, progress checkboxes, and presenter view.
Railway CLI sign-in was checked, but deployment is intentionally reserved for the live class.
Azure and AWS have optional CLI walkthroughs (not deployed or cloud-tested). Use the classroom branch for this version of the lab.

The student ZIP includes source and `.env.example`, not the instructor's `.env` or credentials.
Students can extract it and skip the guide's Git clone step.
