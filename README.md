# Aplyra

Your personal AI job-search agent

Stop applying. Start interviewing.

Small proof of concept using the open-source [Browser Use](https://github.com/browser-use/browser-use) agent. It starts a visible Chromium browser, reads a job application, fills supported fields from a local profile, uploads a PDF resume, and checks for confirmation. The included employer form runs only on your computer.

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

The remote prototype runs Chromium and the mock employer inside one Fly Machine. `/workspace` is a persistent volume for the private profile, resume, browser session, and run logs. The control API has no public HTTP service; `remote.py` connects through a temporary Fly private-network tunnel and requires a bearer token.

Install [flyctl](https://fly.io/docs/flyctl/install/) and sign in with `fly auth login`. In `.env`, set `FLY_APP_NAME` to a unique app name and `APLYRA_CONTROL_TOKEN` to a long random value. Select an API model with `LLM_PROVIDER=openai`, `OPENAI_MODEL`, and `OPENAI_API_KEY`, or set `OLLAMA_HOST` to an Ollama server reachable from Fly. The remote Machine does not run Ollama itself.

```powershell
.venv\Scripts\python.exe remote.py deploy
.venv\Scripts\python.exe remote.py setup --profile profile.json --resume resume.pdf
.venv\Scripts\python.exe remote.py apply --url http://localhost:8000/apply
.venv\Scripts\python.exe remote.py status RUN_ID
```

The `apply` command returns a run ID immediately. Repeat `status` until it reports `confirmed`, `unconfirmed`, or `error`. A stopped Machine leaves a run marked `interrupted` on its next start. For a real site, add `--authorize-url` with **the exact same URL** passed to `--url`. The browser profile persists on the volume, so account sessions can be reused after login. The worker runs one application at a time. Run logs and screenshots stay on the private volume.

`python remote.py tunnel` keeps a tunnel open at `http://127.0.0.1:18080` for diagnostics. The CLI opens and closes its own tunnel for `setup`, `apply`, and `status`.

The remote worker is the first infrastructure step. Job discovery, deduplication, Gmail monitoring, and the CLI question inbox are not implemented yet. Docker and Fly deployment must be exercised where Docker and Fly credentials are available.
