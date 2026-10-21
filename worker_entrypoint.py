"""Start the local demo employer and private worker API."""

import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import uvicorn

from mock_site import ApplicationHandler
from worker import create_app


def main():
    token = os.environ.get("APLYRA_CONTROL_TOKEN")
    if not token:
        raise RuntimeError("APLYRA_CONTROL_TOKEN is required")
    workspace = Path("/workspace")
    ApplicationHandler.output_dir = workspace / "mock_submissions"
    mock = ThreadingHTTPServer(("127.0.0.1", 8000), ApplicationHandler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()
    uvicorn.run(create_app(workspace, token), host="::", port=8080)


if __name__ == "__main__":
    main()
