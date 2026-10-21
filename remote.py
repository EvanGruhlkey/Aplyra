"""Manage one private Fly worker and send applications through a local tunnel."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
from contextlib import contextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv

from agent import is_mock_url, load_profile


LOCAL_PORT = 18080
BASE_URL = f"http://127.0.0.1:{LOCAL_PORT}"


def fly_executable() -> str:
    executable = os.environ.get("FLYCTL_PATH") or shutil.which("flyctl") or shutil.which("fly")
    if not executable:
        raise RuntimeError("Install flyctl or set FLYCTL_PATH to its executable")
    return executable


def require_exact_authorization(url: str, authorized_url: str | None) -> None:
    if not is_mock_url(url) and authorized_url != url:
        raise ValueError("Real-site submission requires authorization for the exact URL")


def deploy_commands(app: str, region: str, app_exists: bool, volume_exists: bool) -> list[list[str]]:
    commands = []
    if not app_exists:
        commands.append(["apps", "create", app])
    if not volume_exists:
        commands.append(["volumes", "create", "data", "--size", "8", "--region", region, "--app", app, "--yes"])
    commands.append(["deploy", "--app", app, "--remote-only", "--ha=false"])
    return commands


def fly(args: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run([fly_executable(), *args], input=input_text, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(f"Fly command failed: {' '.join(args[:2])}")
    return result


def app_name() -> str:
    name = os.environ.get("FLY_APP_NAME", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", name):
        raise ValueError("Set FLY_APP_NAME to a valid Fly app name")
    return name


def control_token() -> str:
    token = os.environ.get("APLYRA_CONTROL_TOKEN", "")
    if len(token) < 24:
        raise ValueError("Set APLYRA_CONTROL_TOKEN to a random value of at least 24 characters")
    return token


def deploy(app: str) -> None:
    token = control_token()
    region = tomllib.loads(Path("fly.toml").read_text(encoding="utf-8"))["primary_region"]
    if not re.fullmatch(r"[a-z]{3}", region):
        raise ValueError("primary_region in fly.toml must be a three-letter Fly region")
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY for the remote worker")
    if provider not in {"openai", "ollama"}:
        raise ValueError("LLM_PROVIDER must be openai or ollama")
    names = ["APLYRA_CONTROL_TOKEN", "LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_BASE_URL", "OLLAMA_HOST", "OLLAMA_MODEL"]
    values = {name: os.getenv(name, "") for name in names}
    values["APLYRA_CONTROL_TOKEN"] = token
    values["LLM_PROVIDER"] = provider
    if provider == "ollama":
        values["OLLAMA_HOST"] = "http://127.0.0.1:11434"
        values["OLLAMA_MODEL"] = os.getenv("REMOTE_OLLAMA_MODEL", "qwen3:4b")
    if any("\n" in value or "\r" in value for value in values.values()):
        raise ValueError("Secret values must be single-line")
    app_exists = fly(["status", "--app", app], check=False).returncode == 0
    if not app_exists:
        fly(["apps", "create", app])
    volumes = fly(["volumes", "list", "--app", app, "--json"])
    try:
        volume_exists = any((volume.get("name") or volume.get("Name")) == "data" for volume in json.loads(volumes.stdout))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Could not read Fly volumes") from exc
    if not volume_exists:
        fly(["volumes", "create", "data", "--size", "8", "--region", region, "--app", app, "--yes"])
    fly(["secrets", "import", "--app", app], input_text="".join(f"{key}={value}\n" for key, value in values.items() if value))
    fly(["deploy", "--app", app, "--remote-only", "--ha=false"])
    print(f"Worker deployed to {app}. Use `python remote.py setup` to upload your files.")


@contextmanager
def tunnel(app: str):
    process = subprocess.Popen([fly_executable(), "proxy", f"{LOCAL_PORT}:8080", "--app", app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("Fly tunnel exited before the worker was ready")
            try:
                if httpx.get(BASE_URL + "/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        else:
            raise RuntimeError("Worker did not respond through the Fly tunnel")
        yield
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def request(method: str, path: str, **kwargs) -> dict:
    headers = {"Authorization": f"Bearer {control_token()}"}
    response = httpx.request(method, BASE_URL + path, headers=headers, timeout=30, **kwargs)
    response.raise_for_status()
    return response.json()


def setup(profile: Path, resume: Path) -> None:
    load_profile(profile, resume)
    request("PUT", "/profile", content=profile.read_bytes())
    request("PUT", "/resume", content=resume.read_bytes())
    print("Profile and resume uploaded.")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Manage one private Aplyra worker")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("deploy")
    sub.add_parser("tunnel")
    setup_parser = sub.add_parser("setup")
    setup_parser.add_argument("--profile", type=Path, default=Path("profile.json"))
    setup_parser.add_argument("--resume", type=Path, default=Path("resume.pdf"))
    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--url", required=True)
    apply_parser.add_argument("--authorize-url", help="Exact real application URL approved for submission")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("run_id")
    args = parser.parse_args()
    try:
        app = app_name()
        if args.command == "deploy":
            deploy(app)
        elif args.command == "tunnel":
            with tunnel(app):
                print(f"Private worker available at {BASE_URL}. Press Ctrl+C to close the tunnel.")
                while True:
                    time.sleep(1)
        else:
            if args.command == "apply":
                require_exact_authorization(args.url, args.authorize_url)
            with tunnel(app):
                if args.command == "setup":
                    setup(args.profile, args.resume)
                elif args.command == "apply":
                    print(json.dumps(request("POST", "/applications", json={"url": args.url, "authorized_url": args.authorize_url}), indent=2))
                elif args.command == "status":
                    print(json.dumps(request("GET", f"/applications/{args.run_id}"), indent=2))
    except (ValueError, RuntimeError, OSError, httpx.HTTPError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
