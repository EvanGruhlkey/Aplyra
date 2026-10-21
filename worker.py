"""Private control API for one applicant worker."""

import json
import os
import threading
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel

from agent import is_mock_url, load_profile, run_application


MAX_UPLOAD = 10_000_000


class ApplicationRequest(BaseModel):
    url: str
    authorized_url: str | None = None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_profile(profile: dict) -> None:
    contact = profile.get("contact", {})
    if not isinstance(contact, dict) or not all(contact.get(k) for k in ("full_name", "email", "phone")):
        raise ValueError("Complete contact.full_name, contact.email, and contact.phone")
    if not profile.get("education") or not profile.get("work_experience"):
        raise ValueError("Complete education and work_experience")
    answers = profile.get("answers", {})
    if not isinstance(answers, dict) or not all(answers.get(k) for k in ("work_authorization", "why_interested")):
        raise ValueError("Complete common answers")


def create_app(workspace: Path, control_token: str, runner=run_application) -> FastAPI:
    if not control_token:
        raise ValueError("APLYRA_CONTROL_TOKEN is required")
    workspace.mkdir(parents=True, exist_ok=True)
    runs = workspace / "runs"
    runs.mkdir(exist_ok=True)
    for status_file in runs.glob("*/status.json"):
        try:
            state = json.loads(status_file.read_text(encoding="utf-8"))
            if state.get("status") == "running":
                state["status"] = "interrupted"
                atomic_write(status_file, json.dumps(state).encode())
        except (OSError, ValueError):
            continue
    app = FastAPI()
    lock = threading.Lock()
    active = {"run_id": None}

    def authenticate(request: Request) -> None:
        import hmac
        if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {control_token}"):
            raise HTTPException(401, "Unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.put("/profile", dependencies=[Depends(authenticate)])
    async def put_profile(request: Request):
        data = await request.body()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Profile too large")
        try:
            profile = json.loads(data)
            if not isinstance(profile, dict):
                raise ValueError("Profile must be an object")
            validate_profile(profile)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        atomic_write(workspace / "profile.json", json.dumps(profile, indent=2).encode())
        return {"status": "saved"}

    @app.put("/resume", dependencies=[Depends(authenticate)])
    async def put_resume(request: Request):
        data = await request.body()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Resume too large")
        if not data.startswith(b"%PDF-"):
            raise HTTPException(400, "Resume must be a PDF")
        atomic_write(workspace / "resume.pdf", data)
        return {"status": "saved"}

    @app.post("/applications", status_code=202, dependencies=[Depends(authenticate)])
    def start_application(body: ApplicationRequest):
        if not is_mock_url(body.url) and body.authorized_url != body.url:
            raise HTTPException(400, "Authorize the exact application URL")
        try:
            load_profile(workspace / "profile.json", workspace / "resume.pdf")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        with lock:
            if active["run_id"]:
                raise HTTPException(409, "An application is already running")
            run_id = uuid.uuid4().hex
            active["run_id"] = run_id
        run_dir = runs / run_id
        run_dir.mkdir()
        state = {"run_id": run_id, "url": body.url, "status": "running"}
        atomic_write(run_dir / "status.json", json.dumps(state).encode())

        def work():
            try:
                result = runner(url=body.url, profile_path=workspace / "profile.json", resume_path=workspace / "resume.pdf", output_dir=run_dir, authorized_url=body.authorized_url, headless=True, browser_data_dir=workspace / "browser")
                state.update(result)
            except Exception as exc:
                state.update(status="error", error=f"{type(exc).__name__}: {exc}")
            finally:
                atomic_write(run_dir / "status.json", json.dumps(state, default=str).encode())
                with lock:
                    active["run_id"] = None

        threading.Thread(target=work, daemon=True).start()
        return {"run_id": run_id, "status": "running"}

    @app.get("/applications/{run_id}", dependencies=[Depends(authenticate)])
    def get_application(run_id: str):
        if not run_id.isalnum():
            raise HTTPException(404, "Run not found")
        path = runs / run_id / "status.json"
        if not path.exists():
            raise HTTPException(404, "Run not found")
        return json.loads(path.read_text(encoding="utf-8"))

    return app
