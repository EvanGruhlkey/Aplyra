# Aplyra

Your personal AI job-search agent

Stop applying. Start interviewing.

Small proof of concept using the open-source [Browser Use](https://github.com/browser-use/browser-use) agent. It starts Chromium, reads a job application, fills supported fields from a profile, uploads a PDF resume, and checks for confirmation. The included employer form can run on your computer or inside the remote worker.

## Setup

Use Python 3.12 or newer. On Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\browser-use.exe install
Copy-Item .env.example .env
Copy-Item profile.example.json profile.json
```

Install [Ollama](https://ollama.com/download), start its service, and run `ollama pull qwen3:8b`. You can instead select an API model in `.env` with `LLM_PROVIDER=openai`, `OPENAI_MODEL`, and `OPENAI_API_KEY`.

Fill `profile.json` with your own contact details, education, work experience, and truthful saved answers. Put your actual PDF at `resume.pdf`. These files and `.env` are ignored by Git because they contain personal information. The included profile has blank fields and intentionally fails validation until completed.

## Run the local test application

In one terminal:

```powershell
.venv\Scripts\python.exe mock_site.py
```

In another terminal:

```powershell
.venv\Scripts\python.exe agent.py --url http://localhost:8000/apply
```

The mock form saves submissions in `mock_submissions/`. The agent saves its final screenshot, conversation logs, and result under `runs/`. A successful local run reports an application ID from the confirmation URL. If the agent cannot finish or confirm submission, it exits with an error and leaves the logs for inspection.

For a real application URL, you must add `--authorize-submit`. This flag authorizes the agent to submit **once** to that site; without it, the browser will not start. Review the target URL and your profile before using the flag. CAPTCHA, MFA, site errors, and missing answers are stop conditions in the agent instructions. Model behavior can vary, so inspect the saved result before relying on a submission.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

These automated tests cover the mock form, PDF upload storage, profile validation, and the real-site authorization gate. A complete browser run also needs Chromium, a running Ollama service with `qwen3:8b` (or an API key), and a filled profile plus resume.

## One-user remote worker

The remote prototype runs Chromium and the mock employer inside one worker container. `/workspace` is persistent storage for the private profile, resume, browser session, and run logs. The control API requires a bearer token and should only be reachable through a private connection.

Install [flyctl](https://fly.io/docs/flyctl/install/) and sign in with `flyctl auth login`. In `.env`, set `FLY_APP_NAME` to a unique app name and `APLYRA_CONTROL_TOKEN` to a long random value. By default, the remote Machine runs Ollama with Qwen3-4B on its own CPU; the model is downloaded to the persistent volume at first startup. Your computer can be turned off after setup. For API inference instead, set `LLM_PROVIDER=openai`, `OPENAI_MODEL`, and `OPENAI_API_KEY` before deployment.

```powershell
.venv\Scripts\python.exe remote.py deploy
.venv\Scripts\python.exe remote.py setup --profile profile.json --resume resume.pdf
.venv\Scripts\python.exe remote.py apply --url http://localhost:8000/apply
.venv\Scripts\python.exe remote.py status RUN_ID
```

The `apply` command returns a run ID immediately. Repeat `status` until it reports `confirmed`, `unconfirmed`, or `error`. A stopped Machine leaves a run marked `interrupted` on its next start. For a real site, add `--authorize-url` with **the exact same URL** passed to `--url`. The browser profile persists on the volume, so account sessions can be reused after login. The worker runs one application at a time. Run logs and screenshots stay on the private volume.

The Ollama configuration in `fly.toml` requests a continuously running 2-shared-CPU, 4 GB Machine and an 8 GB volume. Fly bills for both resources; check its current pricing before deploying. The first startup may take several minutes while Qwen3-1.7B downloads. This smaller model fits accounts limited to 4 GB Machines, though it may need more attempts on complex forms.

Fly trial Machines stop after five minutes until a payment card is added to the Fly account. The local model may need longer than that for a full application, so add a card before running the remote mock test.

`python remote.py tunnel` keeps a tunnel open at `http://127.0.0.1:18080` for diagnostics. The CLI opens and closes its own tunnel for `setup`, `apply`, and `status`.

### AWS EC2 test worker

The same Dockerfile runs on a private EC2 instance. The current one-user test uses Amazon Linux 2023, Docker, an encrypted EBS disk, and Systems Manager for access. Its security group has no inbound rules. Keep `profile.json`, `resume.pdf`, and a random control token in a private directory on the instance, mounted as `/workspace`. The API is published on the instance's loopback address only:

```bash
docker build -t aplyra-worker .
docker run -d --name aplyra-worker --restart unless-stopped --shm-size=1g \
  -p 127.0.0.1:8080:8080 -v /opt/aplyra-data:/workspace \
  -e APLYRA_CONTROL_TOKEN="$(cat /opt/aplyra-data/token)" \
  -e OLLAMA_MODEL=qwen3:4b -e OLLAMA_USE_VISION=false \
  -e OLLAMA_NUM_CTX=16384 aplyra-worker
```

From an instance shell, start and check the mock run:

```bash
curl -sS -X POST http://127.0.0.1:8080/applications \
  -H "Authorization: Bearer $(cat /opt/aplyra-data/token)" \
  -H 'Content-Type: application/json' \
  -d '{"url":"http://localhost:8000/apply"}'
curl -sS http://127.0.0.1:8080/applications/RUN_ID \
  -H "Authorization: Bearer $(cat /opt/aplyra-data/token)"
```

The remote browser runs headlessly; screenshots and conversation logs are saved under `/opt/aplyra-data/runs/RUN_ID/`. Ollama with Qwen3-4B is slow on a two CPU core instance. Stop the EC2 instance after testing if it does not need to stay online.

The intended setup is one small VM per user, with a job finder, application agent, and Gmail monitor running locally on that VM. Each agent can queue questions for the user. This prototype currently runs only the application agent; job discovery, deduplication, Gmail monitoring, and the CLI question inbox are not implemented yet.

The AWS CPU test has not yet produced a confirmed mock application. The saved Browser Use runs and screenshots show the current local model navigating the form but failing to complete it. Treat remote submission as unverified until a run returns `confirmed` and the mock employer records an application ID.
