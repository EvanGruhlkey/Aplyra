"""Small local employer form for exercising the browser agent."""

import argparse
import json
import logging
import uuid
from email.parser import BytesParser
from email.policy import default
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


FORM = """<!doctype html><html lang="en"><meta charset="utf-8"><title>Apply at Aplyra Demo</title>
<h1>Software Engineer application</h1><p>Apply to our local demo employer.</p>
<form action="/apply" method="post" enctype="multipart/form-data">
<label>Full name <input name="full_name" required></label><br>
<label>Email <input name="email" type="email" required></label><br>
<label>Phone <input name="phone" type="tel" required></label><br>
<label>Education <textarea name="education" required></textarea></label><br>
<label>Work experience <textarea name="experience" required></textarea></label><br>
<label>Are you authorized to work in the US? <select name="work_authorization" required><option value="">Select</option><option>Yes</option><option>No</option></select></label><br>
<label>Why are you interested? <textarea name="why_interested" required></textarea></label><br>
<label>Resume PDF <input name="resume" type="file" accept=".pdf,application/pdf" required></label><br>
<button type="submit">Submit application</button></form></html>"""


class ApplicationHandler(BaseHTTPRequestHandler):
    output_dir = Path("mock_submissions")

    def respond(self, code, body, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/apply":
            return self.respond(200, FORM)
        if self.path.startswith("/confirmation/"):
            application_id = self.path.removeprefix("/confirmation/")
            if (self.output_dir / f"{application_id}.json").exists():
                return self.respond(200, f"<h1>Application submitted</h1><p>Application ID: {escape(application_id)}</p>")
        self.respond(404, "Not found")

    def do_POST(self):
        if self.path != "/apply":
            return self.respond(404, "Not found")
        size = int(self.headers.get("Content-Length", "0"))
        if size <= 0 or size > 10_000_000:
            return self.respond(400, "Invalid upload size")
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data;"):
            return self.respond(400, "Expected multipart form")
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + self.rfile.read(size)
        )
        fields = {}
        resume = None
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if name == "resume":
                resume = part.get_payload(decode=True)
            elif name:
                fields[name] = part.get_content().strip()
        required = ("full_name", "email", "phone", "education", "experience", "work_authorization", "why_interested")
        if any(not fields.get(key) for key in required) or not resume or not resume.startswith(b"%PDF-"):
            return self.respond(400, "Missing required information or PDF resume")
        application_id = uuid.uuid4().hex[:12]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / f"{application_id}.json").write_text(json.dumps(fields, indent=2), encoding="utf-8")
        (self.output_dir / f"{application_id}.pdf").write_bytes(resume)
        self.send_response(303)
        self.send_header("Location", f"/confirmation/{application_id}")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    server = ThreadingHTTPServer((args.host, args.port), ApplicationHandler)
    print(f"Mock application: http://{args.host}:{args.port}/apply")
    server.serve_forever()


if __name__ == "__main__":
    main()
