"""Start the local demo employer and private worker API."""

import os
import subprocess
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import uvicorn

from mock_site import ApplicationHandler
from worker import create_app


def main():
    token = os.environ.get("APLYRA_CONTROL_TOKEN")
    if not token:
        raise RuntimeError("APLYRA_CONTROL_TOKEN is required")
    workspace = Path("/workspace")
    if os.getenv("LLM_PROVIDER", "ollama") == "ollama" and os.getenv("OLLAMA_HOST", "127.0.0.1:11434") in {"127.0.0.1:11434", "http://127.0.0.1:11434", "http://localhost:11434"}:
        model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
        server = subprocess.Popen(["ollama", "serve"])
        for _ in range(120):
            if server.poll() is not None:
                raise RuntimeError("ollama serve exited")
            try:
                with urlopen("http://127.0.0.1:11434/api/tags", timeout=1):
                    break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("ollama serve did not become ready")
        subprocess.run(["ollama", "pull", model], check=True, timeout=1800)
    ApplicationHandler.output_dir = workspace / "mock_submissions"
    mock = ThreadingHTTPServer(("127.0.0.1", 8000), ApplicationHandler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    uvicorn.run(create_app(workspace, token), host="::", port=8080)


if __name__ == "__main__":
    main()
