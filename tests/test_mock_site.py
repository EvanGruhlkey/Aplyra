import threading
import urllib.request
from http.server import ThreadingHTTPServer

from mock_site import ApplicationHandler


def test_application_submission(tmp_path):
    ApplicationHandler.output_dir = tmp_path
    server = ThreadingHTTPServer(("127.0.0.1", 0), ApplicationHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(base + "/apply") as response:
            page = response.read().decode()
        assert 'type="file"' in page
        assert 'name="email"' in page

        boundary = "test-boundary"
        fields = {"full_name": "Test Person", "email": "test@example.com", "phone": "5551234567", "education": "Test University", "experience": "Test role", "work_authorization": "Yes", "why_interested": "The work fits my experience."}
        body = b"".join(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
            for key, value in fields.items()
        )
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"resume\"; filename=\"resume.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode() + b"%PDF-1.4\n%%EOF\n" + f"\r\n--{boundary}--\r\n".encode())
        request = urllib.request.Request(base + "/apply", data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(request) as response:
            confirmation = response.read().decode()
            url = response.url
        assert "/confirmation/" in url
        assert "Application ID" in confirmation
        assert len(list(tmp_path.glob("*.json"))) == 1
        assert len(list(tmp_path.glob("*.pdf"))) == 1
    finally:
        server.shutdown()
        server.server_close()
