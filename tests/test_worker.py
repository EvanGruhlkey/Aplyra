import json
import time

from fastapi.testclient import TestClient

from worker import create_app


PROFILE = {"contact": {"full_name": "Test User", "email": "test@example.com", "phone": "1234567890"}, "education": ["School"], "work_experience": ["Work"], "answers": {"work_authorization": "Yes", "why_interested": "Interested"}}


def test_worker_auth_uploads_and_run_failure(tmp_path):
    app = create_app(tmp_path, "secret", runner=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("browser failed")))
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/applications/nope").status_code == 401
    headers = {"Authorization": "Bearer secret"}
    assert client.put("/profile", headers=headers, json=PROFILE).status_code == 200
    assert client.put("/resume", headers=headers, content=b"%PDF-test").status_code == 200
    assert client.put("/resume", headers=headers, content=b"bad").status_code == 400
    assert (tmp_path / "resume.pdf").read_bytes() == b"%PDF-test"
    assert client.put("/resume", headers=headers, content=b"%PDF-" + b"x" * 10_000_000).status_code == 413
    assert client.post("/applications", headers=headers, json={"url": "https://example.com/apply", "authorized_url": "https://elsewhere.com/apply"}).status_code == 400
    response = client.post("/applications", headers=headers, json={"url": "http://localhost:8000/apply"})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(100):
        status = client.get(f"/applications/{run_id}", headers=headers).json()
        if status["status"] != "running":
            break
        time.sleep(0.01)
    assert status["status"] == "error"
    assert json.loads((tmp_path / "runs" / run_id / "status.json").read_text())["status"] == "error"
